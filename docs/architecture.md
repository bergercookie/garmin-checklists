# Architecture

## Why a bridge

The watch could talk to Vikunja directly, but then provider-specific code —
URL shapes, pagination, OAuth refresh — would live in Monkey C, which is slow to
iterate on, hard to test, and updatable only through the app store.

With a bridge:

- the watch speaks one small, stable protocol;
- a new provider is a Python class, not a watch release;
- OAuth providers become possible, because there is somewhere to run a redirect
  handler and hold a refresh token;
- the provider layer has ordinary unit tests.

## The pieces

```text
watch/source/*.mc        Monkey C: menus, local tick state, sync
bridge/src/checklists_bridge/
    models.py            Checklist, SourceRef, validation
    config.py            Environment settings
    security.py          Device token, signed session cookie
    storage.py           One JSON file, written atomically
    providers/           TaskProvider implementations + registry
    service.py           Application logic
    web/                 Watch API, admin API, web UI
```

Dependencies run one way, and `tach` enforces it:

```text
models · config · security  →  providers · storage  →  service  →  web
```

## Data model

A **checklist** is a name and an ordered list of item labels. That is all — no
due dates, no assignees, no completion.

Ids are qualified: `vikunja:12`, `local:9f3c1a7b`. The prefix routes a fetch
without a lookup table. Connect IQ percent-encodes the colon in the URL and the
bridge decodes it back.

## The snapshot

The watch never triggers provider calls per screen. The service keeps a
**snapshot** — the last successful fetch of every selected source.

- `POST /api/v1/admin/refresh` and `GET /api/v1/watch/lists?refresh=true`
  rebuild it.
- Everything else serves the snapshot.

If one source fails, its previous copy is kept and the error reported. A flaky
A provider going down degrades to "slightly stale", never "the watch lost
your checklists".

## Sync

1. `GET /api/v1/watch/lists?refresh=true` → index of `{id, name, count}`
2. `GET /api/v1/watch/lists/{id}` per entry → item labels
3. replace local storage wholesale; every item starts unticked

One list per request keeps peak memory low. Ticks are written to
`Application.Storage` the moment an item is toggled.

## Security

| Boundary | Mechanism |
| --- | --- |
| Watch → bridge | `Authorization: Bearer <device token>`, constant-time compare |
| Browser → bridge | Password login, then an HMAC-signed HttpOnly cookie (30 days) |
| Bridge → provider | Credentials in the data file; redacted before reaching the browser |

TLS is the reverse proxy's job — see [Running the bridge](bridge.md).
