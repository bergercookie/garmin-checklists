# The container image and the compose stack.
#
# Imported by the justfile at the repository root; run these with
# `just <recipe>` from anywhere in the repo, as usual.

# Build the container image locally, the same way the release workflow does.
image-build tag="checklists-bridge:local" version="0+unknown":
    docker build --build-arg APP_VERSION={{version}} -t {{tag}} "{{root}}/bridge"

# Build the image for a release tag and make it say what version it is. The
# image is built from a context with no git history, so the version is handed
# to it -- this is what stops a v1.2.0 image reporting something else.
check-image-version tag:
    #!/usr/bin/env bash
    set -euo pipefail
    expected="{{tag}}"
    expected="${expected#v}"
    docker build --build-arg "APP_VERSION=${expected}" -t checklists-bridge:version-check "{{root}}/bridge"
    actual=$(docker run --rm checklists-bridge:version-check \
        python -c "from checklists_bridge.config import VERSION; print(VERSION)")
    if [ "$actual" != "$expected" ]; then
        echo "FAIL  the image reports ${actual}, expected ${expected}"
        exit 1
    fi
    echo "PASS  the image reports version ${actual}"

# ----------------------------------------------------------------- containers

# Build the bridge image.
docker-build:
    docker compose build

# Start the bridge in the background (needs .env; see .env.example).
docker-up:
    docker compose up -d

# Follow the bridge logs.
docker-logs:
    docker compose logs -f bridge

# Stop the bridge. The data volume is kept.
docker-down:
    docker compose down

# Build the image and prove the container actually serves. This is what CI runs.
image-test:
    #!/usr/bin/env bash
    set -euo pipefail
    # Without the trap, any failure below leaves the container running and the
    # next local run dies with "name already in use" -- a second, confusing
    # error on top of the first.
    trap 'docker rm -f checklists-smoke >/dev/null 2>&1 || true' EXIT
    docker build -t checklists-bridge:ci "{{root}}/bridge"
    docker run -d --name checklists-smoke -e CHECKLISTS_ADMIN_PASSWORD=ci \
        -p 127.0.0.1:8099:8099 checklists-bridge:ci
    for _ in $(seq 1 30); do curl -fsS http://127.0.0.1:8099/healthz && break; sleep 2; done
    curl -fsS http://127.0.0.1:8099/healthz | grep -q '"status":"ok"'
    curl -fsS http://127.0.0.1:8099/login | grep -q 'Checklists bridge'
    curl -fsS -o /dev/null http://127.0.0.1:8099/static/style.css
    just _image-test-unprivileged

# Nothing in the image may run as root, and a bind mount owned by an ordinary
# host user must be writable. Both are easy to break in a Dockerfile edit and
# neither shows up in a health check, so they are asserted rather than assumed.
_image-test-unprivileged:
    #!/usr/bin/env bash
    set -euo pipefail
    uid=$(docker exec checklists-smoke id -u)
    test "$uid" != "0" || { echo "FAIL  the container is running as root"; exit 1; }
    echo "PASS  runs as uid $uid, not root"

    docker exec checklists-smoke test -w /data
    echo "PASS  the default named volume is writable"

    # The case that actually bites people: the state file on the host, owned by
    # a normal login account, with the container told to match it.
    scratch=$(mktemp -d)
    chmod 0777 "$scratch"
    trap 'rm -rf "$scratch"' EXIT
    docker run --rm --user 1234:1234 -v "$scratch:/data" \
        -e CHECKLISTS_ADMIN_PASSWORD=ci checklists-bridge:ci \
        python -c "from pathlib import Path; Path('/data/bridge.json').write_text('{}')"
    test -s "$scratch/bridge.json"
    owner=$(stat -c '%u' "$scratch/bridge.json")
    test "$owner" = "1234" || { echo "FAIL  bind-mounted file owned by $owner"; exit 1; }
    echo "PASS  an overridden uid writes a bind mount, and owns what it writes"
