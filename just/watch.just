# The Garmin app: compiling, packaging and the docs screenshots.
#
# Imported by the justfile at the repository root; run these with
# `just <recipe>` from anywhere in the repo, as usual.

# ---------------------------------------------------------------------- watch
# These need the Connect IQ SDK on PATH and a developer key in CIQ_KEY.

# Compile the watch app for one device at the strictest type-check level.
# Set BRIDGE_URL and DEVICE_TOKEN to compile the pairing in and skip Garmin
# Connect entirely; see tools/build_watch.py for the caveats.
watch-build:
    CIQ_DEVICE={{device}} uv run --project "{{root}}/bridge" python "{{root}}/tools/build_watch.py"

# Refresh the screenshots in docs/images from the real app. Same
# prerequisites as watch-e2e; CIQ_DEVICE picks the device.
screenshots:
    uv run --project "{{root}}/bridge" python "{{root}}/e2e/capture_screenshots.py"

# Warn when docs/images is older than watch/. Needs no SDK; never fails.
screenshots-check:
    uv run --project "{{root}}/bridge" python "{{root}}/tools/check_screenshots.py"

# Compile and launch in the Connect IQ simulator.
watch-sim: watch-build
    connectiq &
    sleep 3
    monkeydo build/checklists-{{device}}.prg {{device}}

# Build the signed .iq bundle for the Connect IQ store / sideloading.
watch-package:
    mkdir -p build
    monkeyc -e -o build/checklists.iq -f watch/monkey.jungle -y "$CIQ_KEY" -w -l 3
