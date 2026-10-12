# Releasing

Tagging is the whole procedure.

```bash
just check          # lint, version drift, tests
git tag v1.2.0
git push origin v1.2.0
```

The `Release` workflow then verifies, builds and publishes.

Verification comes first, so a tag that disagrees with the code, a failing
suite or a broken image stops the run before anything is published. After that
the image goes out and then the GitHub release, in that order — if the release
step itself fails, the image is already published. Re-running the workflow
finishes the job.

**Rehearse it first.** Actions → Release → *Run workflow* builds everything,
including both architectures, and publishes nothing. Worth doing once before
your first real tag, since otherwise the first release is also the first test.

## What comes out

| Artefact | Where |
| --- | --- |
| Container image, amd64 + arm64 | `ghcr.io/OWNER/REPO` — tags `1.2.0`, `1.2`, `1`, `latest` |
| Wheel and sdist | Attached to the GitHub release |
| Release notes | Generated from the commits since the last tag |

A pre-release tag (`v1.3.0-rc1`, anything with a hyphen) publishes only its own
version, is never tagged `latest`, and is marked as a pre-release.

## Where the version comes from

The git tag, via hatch-vcs. Nothing else states it — there is no version to
forget to bump.

Between tags you get `1.2.1.dev4+g1a2b3cd`, which is meant to look wrong if it
ever escapes. The Docker build is the exception: a build context has no git
history, so the version is passed in as `APP_VERSION`, and a plain
`docker build` produces `0+unknown`.

Two checks stop these drifting apart, both in the release workflow:

- `just check-tag v1.2.0` — the code agrees with the tag
- `just check-image-version v1.2.0` — the built image agrees too

If `check-tag` reports a `.dev` version, the tag was not fetched: the checkout
needs `fetch-depth: 0`.

## Nightly images

The `Nightly` workflow builds an image of `main` every night at 03:17 UTC, with
or without a tag. It is for trying what is on `main` before it is released, not
for depending on.

| Tag | Meaning |
| --- | --- |
| `nightly` | The newest nightly. Moves on every build |
| `0.2.1.dev202610120317` | This build. Never moves |
| `sha-1a2b3cd` | The commit it was built from |

It never publishes `latest`, which stays the newest release, and goes to the same
registries as a release (ghcr, and Docker Hub if configured).

- **It skips a night when `main` has not changed** since the last nightly built
  (or last skipped for that same commit). The check is the commit of the newest
  successful run of the workflow, so a night where the build *failed* is tried
  again the next night even if `main` has not moved. Actions → Nightly → *Run
  workflow* with **force** builds regardless.
- **The version is both a Python version and a Docker tag.** It is the next
  release's number as a dated development release -- the latest tag with its
  patch raised (`v0.2.0` leads to `0.2.1`), or the number a pre-release such as
  `v1.3.0-rc1` is heading for -- followed by `.dev` and the UTC minute of the
  build. That is a valid PEP 440 development release, which sorts before the
  release it leads up to, and it uses only characters a registry accepts. It
  avoids `+`: hatch-vcs's own between-tags spelling, `0.2.1.dev4+g1a2b3cd`, has
  one, and a registry refuses it. `just nightly-version` prints what a build
  made now would be called.
- **It runs the same gate as a release** (`just check`, the image's version
  check and the container smoke test) before anything is pushed.
- Old nightlies are not deleted. Prune them in the package's settings, or with a
  retention rule, if they pile up.

## After the first release

The ghcr package is created **private**. Anyone following the install
instructions gets `denied` until you make it public: repository → Packages →
the package → Package settings → Change visibility. Linking it to the
repository at the same time is worth the extra click.

## The Docker Hub image

Off unless configured. In the repository settings add:

| Kind | Name | Value |
| --- | --- | --- |
| Variable | `DOCKERHUB_REPOSITORY` | `yourname/checklists-bridge` |
| Secret | `DOCKERHUB_USERNAME` | your Docker Hub username |
| Secret | `DOCKERHUB_TOKEN` | an access token with write scope |

With the variable unset, releases go to ghcr only and the Docker Hub steps are
skipped.

## Documentation

`docs.yml` publishes the site to GitHub Pages on every push to `main`,
independently of releases. It needs **Settings → Pages → Source: GitHub
Actions** enabled once.
