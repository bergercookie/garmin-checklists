# Adding a provider

One Python class plus one registry entry, and the web UI builds its setup form
for you — the watch never knows which provider a checklist came from.

Each provider is its own subpackage under `providers/`, except the built-in
`local` one, which is a single file because it has nothing to talk to:

```text
providers/
  base.py, registry.py    the contract, shared
  local.py                checklists typed in through the web UI
  vikunja/__init__.py     one file is enough
  trilium/
    __init__.py           the provider and its registry entry
    etapi.py              the HTTP client
    notes.py              turning note text into items
```

Three things beyond the class are worth doing, none of them required:

| | |
| --- | --- |
| `web/static/providers/<id>.svg` | The tile picture. Falls back to `generic.svg`. |
| `docs/<id>.md` | What maps to what, and how to get a token. |
| `e2e/providers/<id>.py` | An end-to-end run; see [testing](testing.md). |

## The contract

```python
class TaskProvider(abc.ABC):
    id: ClassVar[str]  # "vikunja"
    label: ClassVar[str]  # "Vikunja"

    def list_sources(self) -> list[SourceRef]:
        """Everything importable, for the onboarding picker."""

    def fetch(self, source_id: str) -> Checklist:
        """One source as a checklist. Checklist.id is the source id."""
```

There is deliberately no way to write completion back.

If the bridge owns the data (as the built-in `local` provider does), implement
`EditableTaskProvider`, which adds `create_checklist`, `rename_checklist`,
`delete_checklist` and `set_items`.

## Errors

Raise these from `checklists_bridge.providers.base`:

| Exception | When |
| --- | --- |
| `ProviderAuthError` | Credentials rejected (401/403) |
| `ProviderUnavailableError` | Unreachable, timed out, unusable reply |
| `SourceNotFoundError` | The source is gone |

A failed fetch keeps the previous copy of that checklist and reports the error.
It never blanks the watch.

## Registration

```python
SPEC = REGISTRY.register(
    ProviderSpec(
        id="todoist",
        label="Todoist",
        description="Import Todoist projects as checklist templates.",
        factory=lambda config: TodoistProvider(str(config["token"])),
        config_fields=(ConfigField(name="token", label="API token", kind="password"),),
    )
)
```

Then import the module from `providers/__init__.py` so registration runs, and
update the registry assertion in `tests/test_admin_api.py`.

`ConfigField.kind` is `text`, `url`, `password` or `checkbox`. Password fields
are redacted before reaching the browser and survive a re-submit with the
placeholder in place.

## Testing

Inject the HTTP client so no test touches the network:

```python
provider = fake_vikunja({"/api/v2/projects": page([{"id": 12, "title": "Kit"}])})
assert provider.list_sources()[0].name == "Kit"
```

`tests/fakes.py` has an in-memory provider for exercising the service and HTTP
layers without any provider-specific detail.

## Non-list sources

Trilium notes are prose, so the provider has a `notes.py` that turns text into
items and nothing else — no HTTP, no state, every rule a test. Keeping that
apart from the client is what makes the edge cases (entities, `<br>`, ticked
lines, bullets) cheap to pin down. Do the same if your source needs
interpreting rather than reading.

## OAuth providers

Google Tasks and Microsoft To Do need a redirect handler and a stored refresh
token. Add the route under `web/`, keep tokens in the provider's `config` dict
(already treated as secret), and refresh inside the provider — `list_sources`
and `fetch` are the only entry points.
