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
