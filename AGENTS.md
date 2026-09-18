# For coding agents

This repo is friendly to an agent working unattended in a fresh, ephemeral
container: `just install && just check` needs nothing but Python and `uv`. The
one part that is not self-contained is the **Connect IQ SDK** — the real
Garmin toolchain and simulator, used by `watch-build`, `watch-sim`,
`watch-e2e` and `screenshots`. This file is about getting *that* part running
in a cloud sandbox with no GUI, no Garmin account, and a fresh disk every
session. `docs/testing.md` and `docs/watch-app.md` are the human-facing
version; read those first for what each layer proves and why.

## What needs nothing extra

```bash
just test       # pytest, parallel, coverage gate
just lint        # ruff, mypy --strict, tach, file hygiene
just docs        # Sphinx -W
just check-ui    # web UI in Chromium; skips itself if no browser is present
```

`just e2e` (Python stand-in watch, real Vikunja/Trilium) only needs Docker —
see "Docker" below if the daemon is not already running.

## What the Connect IQ SDK needs, and who supplies it

`watch-build`, `watch-sim`, `watch-e2e` and `screenshots` need three things
from Garmin's SDK Manager, a GUI that signs in to a Garmin account. CI cannot
fetch these either (`docs/testing.md` says so), so **ask the user to supply
them** if they are not already present in the environment:

| Path (under `~/.Garmin/ConnectIQ/`, or point `CIQ_SDK` at it) | What | Size |
| --- | --- | --- |
| `Sdks/<version>/bin/{monkeyc,monkeydo,simulator,...}` | The compiler and simulator | ~1 GB |
| `Devices/<device>/` | One directory per target device (`fenix7`, `descentg2`) | small |
| `Fonts/` | The `.cft` files every device references | ~1 GB |

Without `Fonts/` the app compiles and launches, then dies on its first
`drawText` with *Invalid Font Specified* — a build failure this is not; check
for that directory before concluding anything else is wrong.

`e2e/simulator_stack.py` finds the SDK via `CIQ_SDK`, or failing that
`~/.Garmin/ConnectIQ/current-sdk.cfg` (a one-line text file containing the
SDK path). If neither exists but an `Sdks/` directory does, write that file
yourself rather than asking the user to.

### What the user does *not* need to supply: a developer key

A developer key is just an RSA keypair Monkey C signs builds with — it is not
a Garmin credential and does not need to be a real developer's key to build
or run in the simulator. Before asking the user for one:

1. **Check whether one is already staged** in the environment, e.g. under
   `/opt/ciq/key/` or wherever this image's setup put it. Uploaded environments
   observed so far have shipped one already.
2. **If none exists, generate one yourself:**
   ```bash
   openssl genrsa -out developer_key.pem 4096
   openssl pkcs8 -topk8 -inform PEM -outform DER -in developer_key.pem \
       -out developer_key.der -nocrypt
   ```
   This is enough for `watch-build` and the simulator. It is only a problem if
   the user later wants to publish to the Connect IQ store, which needs the
   key registered with Garmin — out of scope for CI/agent work.

**Use the `.der` file, not the `.pem`, as `CIQ_KEY`.** This SDK's `monkeyc -y`
rejects the PKCS8 PEM form with `ERROR: Unable to decode key:
java.security.InvalidKeyException: Unable to decode key`, even though the same
file loads fine with `openssl pkey`. The `.der` form of the same key works
without any other change. If you hit that exact error, this is the fix —
it is not a bad or corrupt key.

## One-time environment prep, every fresh container

None of this survives a container restart, so an agent does it itself each
session rather than asking the user to.

**A display.** The simulator is a GTK app and refuses to start with no X
server (`Can't create a GtkStyleContext without a display connection`):
```bash
Xvfb :99 -screen 0 1280x1024x24 &
export DISPLAY=:99
```

**Docker**, for `e2e`/`watch-e2e`'s real Vikunja/Trilium containers. If
`docker ps` reports it cannot connect to the daemon, the daemon itself simply
is not running yet in this container — start it rather than concluding Docker
is unavailable:
```bash
sudo dockerd > /tmp/dockerd.log 2>&1 &
```
`watch-e2e` also installs a throwaway TLS certificate into the system trust
store via `sudo` (no `-n`: a human at a real terminal gets prompted for a
password instead of it just failing). An agent has no terminal to answer that
prompt on, so passwordless sudo is still what needs to work for that step.

**The library ABI mismatch.** On Ubuntu 24.04 the simulator fails with
```
error while loading shared libraries: libwebkit2gtk-4.0.so.37: cannot open shared object file
```
because it was built against `libwebkit2gtk-4.0`/`libsoup2.4`, and 24.04 only
ships the incompatible `libwebkit2gtk-4.1`/`libsoup-3.0`. This is a real,
documented incompatibility (`docs/watch-app.md`), not a broken install — the
fix is **not** to `apt-get install` the old packages (they are not in 24.04's
repositories, and pulling a `.deb` from elsewhere may not be reachable from a
sandboxed network anyway) but to point `LD_LIBRARY_PATH` at a directory
holding just those old-ABI `.so` files:
```bash
export CIQ_COMPAT_LIBS=/path/to/a/directory/of/old-abi/libs
```
`e2e/simulator_stack.py` already reads `CIQ_COMPAT_LIBS` and wires it into the
simulator's `LD_LIBRARY_PATH` (see `simulator_env()`); running `simulator`
directly, export `LD_LIBRARY_PATH` yourself the same way. Check whether such a
directory is already staged in the environment (e.g. `/opt/ciq/compat/`)
before telling the user this cannot be done here — it very likely already can.

## Running it

```bash
export CIQ_SDK=~/.Garmin/ConnectIQ/Sdks/<version>       # or rely on current-sdk.cfg
export CIQ_KEY=/path/to/developer_key.der               # the .der form
export CIQ_COMPAT_LIBS=/path/to/compat/libs             # see above
export DISPLAY=:99

just watch-build                 # compile only, both devices at type-check level 3
just watch-sim                   # compile + launch in the simulator
just watch-e2e                   # the full chain: real Vikunja, real TLS bridge,
                                  # real compiled app, real simulator, screenshots
```

`watch-e2e` writes screenshots to `build/simulator-screenshots/`; read them
back with the Read tool to confirm what actually happened rather than trusting
exit codes alone — a green run and a correct-looking screen are not always the
same thing to verify by eye once, especially after touching rendering code.

## Testing the background sync service without a real watch or a real hour

`AutoSyncService.onTemporalEvent` (`watch/source/AutoSync.mc`) normally fires
once an hour on a real device. Two things make it reachable in one simulator
session instead:

- **Default is off.** `autoSync` defaults to `false` (a sync clears every
  tick). To exercise the background path, force it on for a throwaway build
  by writing `true` into a copy of
  `watch/resources/properties/autosync.xml` before compiling — do not edit the
  committed file, and never commit a build with this forced on.
- **The simulator can fire the event on demand.** Its menu bar has
  **Simulation → Background Events**, which opens a dialog with **Event Type:
  Temporal Event** and **Target App**. This is greyed out until an app with a
  registered background service is actually running in the simulator.
  Confirming it (via `xdotool` against the `DISPLAY` above, since there is no
  human to click it) invokes `onTemporalEvent()` for real, with no button
  press and no wait — screenshot before and after, and check the bridge's own
  access log for the resulting `GET` requests, rather than trusting that the
  menu click alone proves anything.

## Quick reference: symptom → cause

| Symptom | Cause | Fix |
| --- | --- | --- |
| `Invalid Font Specified` at launch | Missing `Fonts/` | Get the user to supply it; not a code bug |
| `Unable to decode key` from `monkeyc -y` | Key is PEM, not DER | Use the `.der` file for `CIQ_KEY` |
| `libwebkit2gtk-4.0.so.37: cannot open shared object file` | Ubuntu 24.04's ABI mismatch | `CIQ_COMPAT_LIBS` / `LD_LIBRARY_PATH`, not `apt-get` |
| `Can't create a GtkStyleContext without a display connection` | No X server | `Xvfb :99 &`, `export DISPLAY=:99` |
| `Cannot connect to the Docker daemon` | Daemon not started in this container | `sudo dockerd &` |
| `watch-e2e` fails at "certificate installed in the system trust store" | No passwordless `sudo` | `sudo` now prompts rather than just failing, but an agent has nothing to answer that with; ask the user if passwordless sudo does not already work |
| "Background Events" is greyed out in the simulator menu | No app with a background service is currently running | Launch the compiled app first, then open the menu |
