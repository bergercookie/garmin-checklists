# Checklists

A Garmin watch app for checklists — dive kit, pre-flight, packing — backed by a
small self-hosted bridge that pulls them from your task manager.

Works on **fenix 7** and **Descent G2**. Pulls from **Vikunja** and **Trilium
Notes**, or keeps checklists itself; adding a provider is one Python class.

<p align="center">
  <img src="docs/images/fenix7-index.png" alt="The checklist index on a fenix 7" width="240">
  <img src="docs/images/fenix7-checklist-ticked.png" alt="A checklist with an item ticked" width="240">
</p>

```text
┌──────────┐  HTTPS   ┌──────────────┐  HTTPS  ┌─────────┐
│ Watch    │ ───────► │ Bridge       │ ──────► │ Vikunja │
│ Monkey C │  via the │ FastAPI      │         │ …or none│
└──────────┘  phone   └──────────────┘         └─────────┘
      ▲                      ▲
      │ ticks stay here      │ browser: connect, pick lists, edit
      └──────────────────────┘
```

## Who this is for

Productivity-minded homelab users who are comfortable with server work: you keep
a box running, you have a reverse proxy with real certificates, and a compose
file does not frighten you. Setup is about fifteen minutes.

There is no hosted service and no account. You run the bridge; your provider
credentials stay on your disk. HTTPS is mandatory — Connect IQ refuses plain
HTTP outright (see [Running the bridge](docs/bridge.md)).

## Two rules

1. **Checklists flow one way.** The bridge serves templates. Ticks stay on the
   watch and are never written back.
2. **A sync replaces everything and clears every tick.** Items always arrive
   unticked. That is also how you reset a template.

## Quick start

```bash
cp .env.example .env     # admin password + your HTTPS URL
docker compose up -d
```

> **The bridge must sit behind an HTTPS reverse proxy.** The watch refuses plain
> HTTP, and will not trust a certificate your system does not.

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
