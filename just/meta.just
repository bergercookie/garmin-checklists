# Checks on the build tooling itself.
#
# Imported by the justfile at the repository root; run these with
# `just <recipe>` from anywhere in the repo, as usual.

# Check the justfile itself: that it parses, and that CI and the docs drive
# everything through it rather than calling the underlying tools directly.
check-justfile:
    uv run --project "{{root}}/bridge" python "{{root}}/tools/check_justfile.py"

# Check that an untracked justfile.user is imported, adds recipes, and cannot
# silently shadow one of ours.
check-justfile-user:
    uv run --project "{{root}}/bridge" python "{{root}}/tools/check_user_justfile.py"

# Drive the web UI in a real browser: tiles, pictures, keyboard, the sheet.
# Skips itself when Playwright or a browser is missing.
check-ui:
    uv run --project "{{root}}/bridge" python "{{root}}/tools/check_ui.py"
