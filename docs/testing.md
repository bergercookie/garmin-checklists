# Testing

| Layer | Command | Needs | Time |
| --- | --- | --- | --- |
| Unit and HTTP | `just test` | nothing | ~3s |
| End-to-end, simulated watch | `just e2e` | Docker | ~2min |
| One provider only | `just e2e-vikunja`, `just e2e-trilium` | Docker | ~1min |
| The web UI, in a browser | `just check-ui` | Chromium | ~10s |
| End-to-end, real watch app | `just watch-e2e` | Docker + Connect IQ SDK | ~2min |

Everything runs through the justfile. `just check-justfile` fails if a workflow
calls `pytest`, `ruff`, `docker` or `pre-commit` directly, or if the docs name a
recipe that does not exist.

## Python

3.14 or newer. `uv` fetches it; nothing needs installing system-wide.

The floor lives in `bridge/pyproject.toml` and is repeated in four more places
(mypy, ruff's pyupgrade target, `devbox.json`, the Dockerfile). Raise it there
and run `just check-python-version`, which fails if any of them lag behind.

Old syntax is rewritten automatically: ruff's `UP` rules are pyupgrade, and they
follow `target-version` in the root `pyproject.toml`.

## Unit and HTTP

`bridge/tests/` covers models, storage, security, both providers, the service
and the HTTP layer. Provider HTTP is stubbed with `httpx.MockTransport`.

Coverage is on by default (`--cov` is in `addopts`), currently 100%, gated at
`fail_under = 98`. For a focused run: `just test --no-cov -k something`.

`precision = 2` in the coverage config is load-bearing: without it `fail_under`
compares against a total rounded to whole percent, so 97.58% reads as "98" and
slips through.

## End-to-end

`just e2e` runs the same eleven steps against each provider in turn: start it in
a container, seed it, start the bridge, drive the admin API, sync a
simulated watch, tick something, and prove nothing was written back upstream.

Everything provider-shaped lives in `e2e/providers/`; the runner does not know
which one it has. Adding a provider to this layer is one module there and one
line in `full_stack.py`.

The Vikunja run mints a token with only the scopes [vikunja.md](vikunja.md) asks
for. The Trilium run creates the database, sets a password and mints an ETAPI
token over HTTP, with no UI — and seeds a note mixing `[]` lines, an `[x]` line
and prose, so the parser is proved against a real Trilium rather than a fixture
of what one is imagined to return.

Behind a restrictive proxy, override the images: `VIKUNJA_IMAGE=…` and
`TRILIUM_IMAGE=…` (for example a `mirror.gcr.io/` prefix).

`just check-ui` drives the web UI in Chromium. It earns its place: it caught a
`Referrer-Policy: no-referrer` header that made Chrome send `Origin: null` on
the sign-in form, which the bridge's own CSRF check then refused — sign-in was
broken in every real browser while the whole httpx-based suite stayed green. It
skips itself when Playwright or a browser is missing.

This layer found the Vikunja integration's real bugs: a `sort_by` value the API
rejects with 400, a route needing a permission the docs did not ask for, and
saved filters being offered as checklists. None were visible to tests that stub
HTTP.

### What the "watch" is there

`e2e/watch_simulator.py`, not the Garmin simulator — so `just e2e` needs no SDK.
It reimplements the watch's observable behaviour, and **step 0 reads the Monkey
C sources and fails if they no longer agree with it**, so it cannot rot into
fiction. It does not execute Monkey C.

## End-to-end with the real app

`just watch-e2e` runs the same chain with the compiled Monkey C app in the
Connect IQ simulator, then checks the bridge's access log to prove the requests
came from the device. Screenshots land in `build/simulator-screenshots/`.

Two things to know before changing the harness:

- **The watch will not talk to plain HTTP** (`SECURE_CONNECTION_REQUIRED`,
  -1001), so the run serves TLS via `e2e/tls_bridge.py`.
- **It will not trust a certificate the system does not**, and an untrusted one
  surfaces as a bare `404`. The run installs its certificate into the system
  trust store, which needs `sudo`.

It clicks on-screen buttons because the keyboard is only partly mapped, and it
wipes the simulator's state directory first because a stored `.SET` beats the
compiled defaults.

## Screenshots

`just screenshots` walks the app in the simulator and writes `docs/images/`.
The Markdown refers to stable filenames, so refreshing pictures never means
editing prose.

```bash
just screenshots
CIQ_DEVICE=descentg2 just screenshots
```

CI cannot regenerate them: the SDK, device files and ~1 GB of fonts all come
from Garmin's SDK Manager, a GUI that signs in to a Garmin account. So
`just screenshots-check` compares a fingerprint of `watch/**/*.{mc,xml}` against
`docs/images/watch-source.sha256` and **warns** without failing.

<details>
<summary>Fully automatic, on a self-hosted runner with the SDK</summary>

```yaml
  screenshots:
    runs-on: [self-hosted, connectiq]
    steps:
      - uses: actions/checkout@v4
      - run: just screenshots
      - run: CIQ_DEVICE=descentg2 just screenshots
      - uses: stefanzweifel/git-auto-commit-action@v5
        with:
          commit_message: "Refresh the documentation screenshots"
          file_pattern: docs/images/*
```
</details>

## CI

| Workflow | Job | Runs |
| --- | --- | --- |
| CI | `lint` | `just lint`, `just check-justfile` |
| CI | `image` | `just image-test` |
| CI | `screenshots` | `just screenshots-check` |
| Coverage | `coverage` | `just coverage-ci` |
| Docs | `docs` | `just docs` and publishes to GitHub Pages |

Neither end-to-end run is in CI: both need Docker-in-Docker, and the simulator
run needs the SDK.
