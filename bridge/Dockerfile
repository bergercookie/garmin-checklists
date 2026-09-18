# Two stages: resolve dependencies with uv, then ship a plain Python runtime
# containing nothing but the virtualenv.
#
# Everything comes from one registry (Docker Hub) so this still builds behind a
# restrictive mirror or a proxy that only allows one upstream.

FROM python:3.14-slim-trixie AS builder

# Pinned so a rebuild resolves the same way; bump deliberately. It has to be
# new enough to read uv.lock's revision, so bump it with the lockfile.
ARG UV_VERSION=0.12.17

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    PIP_DISABLE_PIP_VERSION_CHECK=1

RUN pip install --no-cache-dir "uv==${UV_VERSION}"

WORKDIR /app

# Dependencies first, so editing source does not invalidate this layer.
COPY pyproject.toml uv.lock ./
RUN uv sync --locked --no-dev --no-install-project

# --no-editable installs a real wheel, so the runtime stage needs the
# virtualenv and nothing else. Templates and static files travel with it.
COPY src ./src

# The version normally comes from `git describe`, but a build context has no
# .git in it (and python:*-slim has no git either), so it is passed in. The
# release workflow sets it from the tag; a plain `docker build` gets the
# placeholder, which is deliberately not a version anybody could mistake for a
# release.
#
# Declared here rather than at the top of the stage, and exported for this one
# command rather than as an ENV, for two reasons: an ENV that changes on every
# tag invalidates every layer below it, so the dependency sync above would be
# rebuilt from scratch for both architectures on every single release; and
# SETUPTOOLS_SCM_PRETEND_VERSION applies to whatever is being built, so it
# should be in scope only while our own package is. The per-distribution
# spelling does not work here -- hatch-vcs does not pass setuptools-scm a
# distribution name, and its own error message says so.
ARG APP_VERSION=0+unknown
RUN SETUPTOOLS_SCM_PRETEND_VERSION="${APP_VERSION}" \
    uv sync --locked --no-dev --no-editable


FROM python:3.14-slim-trixie AS runtime

# 127.0.0.1 is the right default on a laptop and the wrong one in a container.
ENV CHECKLISTS_HOST=0.0.0.0 \
    CHECKLISTS_PORT=8099 \
    CHECKLISTS_DATA_FILE=/data/bridge.json \
    PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1

# Nothing in this image runs as root. The uid is a build argument because a
# bind mount is owned by whoever owns it on the host, and the container has to
# match: either rebuild with --build-arg APP_UID=$(id -u), or leave the image
# alone and override at run time with `user:` in docker-compose.yml, which is
# the easier of the two. See docs/bridge.md.
ARG APP_UID=10001
ARG APP_GID=10001

# Keep a small set of operational tools in the runtime image so connectivity
# and configuration can be diagnosed from inside the container.
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        curl \
        iputils-ping \
        neovim \
        traceroute \
    && rm -rf /var/lib/apt/lists/*

# The data directory is created here so a named volume inherits its ownership.
# Note that overriding `user:` in compose does NOT work with a named volume:
# the volume is created owned by this uid/gid, and an overridden process runs
# under a different gid, so the first write fails. Override the uid only
# together with a bind mount you own -- which is what .env.example says.
RUN groupadd --system --gid "${APP_GID}" checklists \
    && useradd --system --create-home --uid "${APP_UID}" --gid "${APP_GID}" checklists \
    && mkdir -p /data \
    && chown "${APP_UID}:${APP_GID}" /data \
    && chmod 0750 /data

WORKDIR /app
COPY --from=builder --chown=checklists:checklists /app/.venv /app/.venv

# Everything below this line -- including the healthcheck -- runs unprivileged.
USER checklists
EXPOSE 8099
VOLUME ["/data"]

# The port is read from the environment rather than hardcoded: setting
# CHECKLISTS_PORT used to give a permanently unhealthy container that was in
# fact working perfectly.
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import os, urllib.request; urllib.request.urlopen('http://127.0.0.1:' + os.environ.get('CHECKLISTS_PORT', '8099') + '/healthz', timeout=4)"

CMD ["checklists-bridge"]
