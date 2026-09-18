// Web UI. Deliberately dependency-free: one fetch helper, one render pass.
const API = "/api/v1/admin";

const $ = (id) => document.getElementById(id);

async function call(method, path, body) {
  const response = await fetch(API + path, {
    method,
    headers: body ? { "Content-Type": "application/json" } : {},
    body: body ? JSON.stringify(body) : undefined,
  });
  if (response.status === 401) {
    window.location.href = "/login";
    throw new Error("signed out");
  }
  if (!response.ok) {
    const payload = await response.json().catch(() => ({}));
    throw new Error(payload.detail || `HTTP ${response.status}`);
  }
  return response.status === 204 ? null : response.json();
}

function flash(message, kind = "ok") {
  const element = $("flash");
  element.textContent = message;
  element.dataset.kind = kind;
  element.hidden = false;
}

async function guard(action) {
  try {
    await action();
  } catch (error) {
    flash(error.message, "error");
  }
}

function element(tag, props = {}, children = []) {
  const node = Object.assign(document.createElement(tag), props);
  for (const child of children) node.append(child);
  return node;
}

async function copyToClipboard(text) {
  // navigator.clipboard needs a secure context; fall back for plain HTTP.
  if (navigator.clipboard && window.isSecureContext) {
    await navigator.clipboard.writeText(text);
    return;
  }
  const scratch = element("textarea", { value: text, readOnly: true });
  scratch.style.position = "fixed";
  scratch.style.opacity = "0";
  document.body.append(scratch);
  scratch.select();
  document.execCommand("copy");
  scratch.remove();
}

function wireCopyButtons() {
  for (const button of document.querySelectorAll("button.copy")) {
    button.onclick = () =>
      guard(async () => {
        await copyToClipboard($(button.dataset.copy).textContent.trim());
        const original = button.textContent;
        button.textContent = "Copied";
        button.dataset.done = "1";
        setTimeout(() => {
          button.textContent = original;
          delete button.dataset.done;
        }, 1500);
      });
  }
}

function renderPairing(state) {
  $("public-url").textContent = state.public_url || "(set CHECKLISTS_PUBLIC_URL)";
  $("device-token").textContent = state.device_token;
}

function renderSummary(state) {
  const items = state.snapshot.reduce((total, list) => total + list.items.length, 0);
  $("sum-lists").textContent = state.snapshot.length;
  $("sum-items").textContent = items;
  $("sum-synced").textContent = state.synced_at
    ? new Date(state.synced_at * 1000).toLocaleString()
    : "never";

  // A provider whose token expired keeps serving the last good copy for ever.
  // Saying so here is the only way the user finds out before the checklists are
  // months out of date.
  const stale = $("sum-stale");
  if (state.sync_errors && state.sync_errors.length) {
    const tried = state.last_attempt_at
      ? new Date(state.last_attempt_at * 1000).toLocaleString()
      : "recently";
    stale.textContent = `Last attempt (${tried}) failed: ${state.sync_errors.join("; ")}. The watch is seeing the copy above.`;
    stale.hidden = false;
  } else {
    stale.hidden = true;
  }
  $("snapshot").replaceChildren(
    ...state.snapshot.map((list) =>
      element("li", { textContent: `${list.name} — ${list.items.length} item(s)` }),
    ),
  );
}

function configForm(provider) {
  // The inputs are held in this map rather than looked up by id at save time:
  // the form now lives inside a dialog, and a document-wide getElementById is
  // one duplicated render away from finding somebody else's field.
  const fields = new Map();

  const inputs = provider.fields.map((field) => {
    const saved = provider.config[field.name];
    const input = element("input", {
      id: `${provider.id}-${field.name}`,
      name: field.name,
      type:
        field.kind === "checkbox"
          ? "checkbox"
          : field.kind === "password"
            ? "password"
            : field.kind === "url"
              ? "url"
              : "text",
      placeholder: field.placeholder,
    });
    if (field.kind === "checkbox") input.checked = saved ?? field.default;
    else input.value = saved ?? field.default ?? "";
    fields.set(field.name, { field, input });
    return element("div", {}, [
      element("label", { textContent: field.label, htmlFor: input.id }),
      input,
      field.help ? element("p", { className: "muted", textContent: field.help }) : "",
    ]);
  });

  const save = element("button", { textContent: "Save and test" });
  save.onclick = () =>
    guard(async () => {
      const config = {};
      for (const [name, { field, input }] of fields) {
        config[name] = field.kind === "checkbox" ? input.checked : input.value.trim();
      }
      await call("PUT", `/providers/${provider.id}/config`, { config });
      flash(`${provider.label} connected. Now pick the checklists to import.`);
      await load();
    });

  const actions = [save];
  // Nothing to disconnect from until it has been connected once.
  if (provider.configured) {
    const forget = element("button", { textContent: "Disconnect", className: "danger" });
    forget.onclick = () =>
      guard(async () => {
        await call("DELETE", `/providers/${provider.id}/config`);
        closeSheet();
        await load();
      });
    actions.push(forget);
  }

  return element("div", {}, [...inputs, element("div", { className: "row" }, actions)]);
}

async function sourcePicker(provider) {
  const container = element("div", {});
  const { sources } = await call("GET", `/providers/${provider.id}/sources`);
  if (!sources.length) {
    container.append(element("p", { className: "muted", textContent: "Nothing to import yet." }));
    return container;
  }
  const list = element("ul", { className: "sources" });
  for (const source of sources) {
    const box = element("input", { type: "checkbox", id: `${provider.id}-src-${source.id}` });
    box.checked = provider.selected.includes(String(source.id));
    box.dataset.sourceId = source.id;
    list.append(
      element("li", {}, [box, element("label", { htmlFor: box.id, textContent: source.name })]),
    );
  }
  const save = element("button", { textContent: "Import selected" });
  save.onclick = () =>
    guard(async () => {
      const chosen = [...list.querySelectorAll("input:checked")].map((box) => box.dataset.sourceId);
      await call("PUT", `/providers/${provider.id}/selection`, { source_ids: chosen });
      await call("POST", "/refresh");
      flash(`Imported ${chosen.length} checklist(s) from ${provider.label}.`);
      await load();
    });
  container.append(
    element("p", { className: "muted", textContent: "Which lists should reach the watch?" }),
    list,
    save,
  );
  return container;
}

function localEditor(state) {
  const container = element("div", {});
  for (const checklist of state.local_checklists) {
    const name = element("input", { value: checklist.name });
    const items = element("textarea", { rows: 4, value: checklist.items.join("\n") });
    const save = element("button", { textContent: "Save" });
    save.onclick = () =>
      guard(async () => {
        await call("PUT", `/local/checklists/${checklist.id}`, {
          name: name.value,
          items: items.value.split("\n"),
        });
        await call("POST", "/refresh");
        flash(`Saved "${name.value}".`);
        await load();
      });
    const remove = element("button", { textContent: "Delete", className: "danger" });
    remove.onclick = () =>
      guard(async () => {
        await call("DELETE", `/local/checklists/${checklist.id}`);
        await call("POST", "/refresh");
        await load();
      });
    container.append(
      element("div", { className: "checklist" }, [
        element("label", { textContent: "Name" }),
        name,
        element("label", { textContent: "Items, one per line" }),
        items,
        element("div", { className: "row" }, [save, remove]),
      ]),
    );
  }

  const newName = element("input", { placeholder: "New checklist name" });
  const add = element("button", { textContent: "Add checklist" });
  add.onclick = () =>
    guard(async () => {
      await call("POST", "/local/checklists", { name: newName.value });
      flash(`Created "${newName.value}".`);
      await load();
    });
  container.append(element("div", { className: "checklist" }, [newName, add]));
  return container;
}

// Which sheet is open. Kept outside the DOM because load() rebuilds the grid
// after every save, which would otherwise close the sheet mid-edit.
let openProvider = null;

function providerStatus(provider, state) {
  if (provider.editable) {
    const count = state.local_checklists.length;
    return count ? `${count} checklist(s)` : "Nothing yet";
  }
  if (!provider.configured) return "Not connected";
  return provider.selected.length
    ? `${provider.selected.length} list(s) imported`
    : "Connected, nothing picked";
}

function providerTile(provider, state) {
  const picture = element("img", {
    src: `/static/providers/${provider.id}.svg`,
    alt: "",
    className: "provider-art",
  });
  // A provider added without art should look plain, not broken.
  picture.onerror = () => {
    picture.src = "/static/providers/generic.svg";
  };

  const tile = element("button", { className: "provider-tile", type: "button" }, [
    picture,
    element("span", { className: "provider-name", textContent: provider.label }),
    element("span", { className: "provider-state", textContent: providerStatus(provider, state) }),
  ]);
  if (provider.configured && !provider.editable) tile.dataset.connected = "1";
  tile.onclick = () => guard(() => openSheet(provider.id));
  return tile;
}

async function openSheet(providerId) {
  const state = await call("GET", "/state");
  const provider = state.providers.find((item) => item.id === providerId);
  if (!provider) return;
  openProvider = providerId;

  const sheet = $("provider-sheet");
  const body = element("div", {}, [
    element("p", { className: "muted", textContent: provider.description }),
  ]);
  if (provider.editable) {
    body.append(localEditor(state));
  } else {
    body.append(configForm(provider));
    if (provider.configured) {
      // Fetched here rather than during the grid render: this used to be one
      // request per configured provider on every one of the eleven renders a
      // session does.
      try {
        body.append(await sourcePicker(provider));
      } catch (error) {
        body.append(element("p", { className: "error", textContent: error.message }));
      }
    }
  }

  $("sheet-title").textContent = provider.label;
  $("sheet-art").src = `/static/providers/${provider.id}.svg`;
  $("sheet-body").replaceChildren(body);
  if (!sheet.open) sheet.showModal();
}

function closeSheet() {
  openProvider = null;
  const sheet = $("provider-sheet");
  if (sheet.open) sheet.close();
}

async function renderProviders(state) {
  $("providers").replaceChildren(
    ...state.providers.map((provider) => providerTile(provider, state)),
  );
  // A save re-renders everything; re-open whatever was being edited so the
  // sheet does not vanish under the person using it.
  if (openProvider) await openSheet(openProvider);
}

async function load() {
  const state = await call("GET", "/state");
  renderPairing(state);
  renderSummary(state);
  await renderProviders(state);
}

$("refresh").onclick = () =>
  guard(async () => {
    const report = await call("POST", "/refresh");
    flash(
      report.ok
        ? `Refreshed ${report.checklists.length} checklist(s).`
        : `Refreshed with problems: ${report.errors.join("; ")}`,
      report.ok ? "ok" : "error",
    );
    await load();
  });

$("rotate-token").onclick = () =>
  guard(async () => {
    await call("POST", "/device-token");
    flash("New token issued — update the watch settings.");
    await load();
  });

// There is no per-device sign-out to offer: the cookie proves only that
// somebody knew the password, so one browser cannot be told apart from another.
$("revoke-sessions").onclick = () =>
  guard(async () => {
    if (!confirm("Sign out every phone, including this one?")) return;
    await call("POST", "/sessions/revoke");
    window.location.href = "/login";
  });

$("sheet-close").onclick = () => closeSheet();
// Esc and the backdrop close a <dialog> natively; keep our own state in step.
$("provider-sheet").addEventListener("close", () => {
  openProvider = null;
});

wireCopyButtons();
guard(load);
