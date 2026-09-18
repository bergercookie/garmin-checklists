# End-to-end runs. Each needs Docker; the watch one also needs the SDK.
#
# Imported by the justfile at the repository root; run these with
# `just <recipe>` from anywhere in the repo, as usual.

# Both providers, end to end. About two minutes. See docs/testing.md.
e2e: e2e-vikunja e2e-trilium

# Real Vikunja in Docker, the bridge as a process, and a simulated watch.
e2e-vikunja:
    uv run --project "{{root}}/bridge" python "{{root}}/e2e/full_stack.py" vikunja

# The same run against real Trilium: notes whose lines start with [].
e2e-trilium:
    uv run --project "{{root}}/bridge" python "{{root}}/e2e/full_stack.py" trilium

# Trust a self-signed cert for 127.0.0.1 system-wide, then exit -- for pointing
# a real device or browser at a bridge you started by hand over HTTPS.
install-cert:
    uv run --project "{{root}}/bridge" python "{{root}}/e2e/full_stack.py" --install-cert

# The whole stack with the REAL watch app in the Connect IQ simulator.
# Needs the SDK, its Devices and Fonts, a developer key, Docker and a display.
watch-e2e:
    uv run --project "{{root}}/bridge" python "{{root}}/e2e/simulator_stack.py"
