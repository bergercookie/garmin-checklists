# Checklists

A Garmin watch app for checklists — dive kit, pre-flight, packing etc. — backed by a
small self-hosted bridge that pulls them from your task manager. Checklists

<p align="center">
  <img src="docs/images/fenix7-index.png" alt="The checklist index on a fenix 7" width="240">
  <img src="docs/images/fenix7-checklist-ticked.png" alt="A checklist with an item ticked" width="240">
</p>

Checklists selected from your TODO manager / note-taking app of choice and are
imported to your Garmin watch.
On the watch you can tick/untick the items in the checklist. The item ticks stay on the
device - i.e, whenever an item is ticked, said new ticked status is not copied
back to the provider. This is deliberate as these checklists are ultimately
considered templates / routine items from the perspective of this tool -
e.g., "Night routine" items that are meant to be executed routinely and don't
need to be checked off in the provider.


```text
┌──────────┐  HTTPS   ┌──────────────┐  HTTPS  ┌─────────────────┐
│ Watch    │ ───────► │ Bridge       │ ──────► │ Vikunja, Trilium│
│ Monkey C │  via the │ FastAPI      │         │ …or none        │
└──────────┘  phone   └──────────────┘         └─────────────────┘
      ▲                      │
      │ send templates       │ browser: connect, pick lists, edit
      └──────────────────────┘
```

## Who this is for

Productivity-minded homelab users who are comfortable with server work: you keep
a box running, you have a reverse proxy with real certificates, and a compose
file does not frighten you.

There is no hosted service and no account. You run the bridge; your provider
credentials stay on your disk. HTTPS is mandatory — Connect IQ refuses plain
HTTP outright (see [Running the bridge](docs/bridge.md)).

## Quick start

```bash
cp .env.example .env     # admin password + your HTTPS URL
docker compose up -d
```

For this to work you have a valid TLS certificate for the bridge server, one
that the client (i.e., the garmin app on your phone) will ultimately trust. It
is advised that you use a reverse proxy in front of the bridge, like
[caddy](https://caddyserver.com/) and set it up with a public TLS certificate authority (e.g., via [Let's Encrypt](https://letsencrypt.org/)).

Then open the bridge in a browser, add checklists, and install the app:
**[Getting started](docs/getting-started.md)**.

## Documentation

| | |
| --- | --- |
| [Getting started](docs/getting-started.md) | Setup, first sync, daily use |
| [Running the bridge](docs/bridge.md) | Docker, reverse proxy, config, backups, several phones |
| [Installing on a watch](docs/install-on-watch.md) | Sideloading, MTP, the `.SET` file |
| [The watch app](docs/watch-app.md) | Using it, building it, troubleshooting |
| [Vikunja](docs/vikunja.md) | Token scopes and what maps to what |
| [Trilium Notes](docs/trilium.md) | `[]` lines, and which notes are offered |
| [Adding a provider](docs/providers.md) | The interface, in one class |
| [Architecture](docs/architecture.md) | How the pieces fit |
| [Testing](docs/testing.md) | The three layers |
| [Releasing](docs/releasing.md) | Tag, and the rest is automatic |

Built as a site with `just docs`.

## Layout

```text
bridge/              FastAPI service, providers, web UI
watch/               Connect IQ application (Monkey C)
e2e/                 End-to-end harnesses
tools/               Build and check scripts
docs/                Documentation (Sphinx + MyST)
docker-compose.yml   Self-hosting template
justfile             Every task; run `just` to list them
```

## Development

**`devbox shell`** gets you the right Python, `uv`, `just` and `pre-commit` in
one step; without it, install Python 3.14+ and `uv` yourself. The version is
set in `bridge/pyproject.toml` and repeated in mypy, ruff, devbox and the
Dockerfile — `just check-python-version` fails if those drift apart.

Everything goes through `just`.

```bash
just install      # create the bridge virtualenv
just test         # pytest, parallel, coverage gate included
just lint         # ruff, mypy --strict, tach, file hygiene
just check        # lint + coverage, i.e. what CI runs
just docs         # build the documentation site
just e2e          # real Vikunja + bridge + simulated watch (Docker)
just watch-build  # compile the watch app (Connect IQ SDK)
```

### Your own recipes

```bash
cp justfile.user.example justfile.user
```

`justfile.user` is untracked and imported automatically; its recipes join the
list. It can only *add* — reusing a name is an error rather than a silent
override, so `just lint` means the same thing on your machine as in CI.

`devbox shell` provides python, uv, just and pre-commit if you want them.
