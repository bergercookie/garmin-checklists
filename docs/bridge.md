# Running the bridge

> **HTTPS is not optional.** Connect IQ refuses a plain-HTTP endpoint, and it
> will not trust a certificate your system does not — an untrusted one surfaces
> as an HTTP `404`, not a TLS error. Terminate TLS in a reverse proxy in front
> of the bridge.

## Docker Compose

`docker-compose.yml` at the repository root is a working template.

```bash
cp .env.example .env
$EDITOR .env
docker compose up -d
curl -s http://127.0.0.1:8099/healthz     # {"status":"ok",...}
```

You get the bridge on `127.0.0.1:8099` (loopback only), a named volume for its
state, a healthcheck, and a non-root container user.

`just docker-up`, `just docker-logs`, `just docker-down` wrap the same commands.

### Existing stacks

Copy the `bridge` service and the `checklists-data` volume into your own
compose file. Point `build:` at this repo's `bridge/`, or build once:

```bash
just image-build checklists-bridge:mine
```

If your proxy is also a container, drop the `ports:` block and put both on the
same network; the proxy then reaches `http://checklists-bridge:8099`.

### File permissions

The container runs as uid 10001, never root. With the default named volume there
is nothing to do.

Bind-mounting the state onto your host — so it lands where your backups already
look — means the container has to write as *you*:

```bash
mkdir -p ./data && sudo chown $(id -u):$(id -g) ./data
printf 'PUID=%s\nPGID=%s\n' "$(id -u)" "$(id -g)" >> .env
```

Then swap the volume line in `docker-compose.yml` for `- ./data:/data`. The
`user:` line already reads `PUID`/`PGID`.

Symptom of getting this wrong: the bridge exits at startup with
`Permission denied` on `/data/bridge.json`.

## Reverse proxy

```caddyfile
checklists.example.com {
    reverse_proxy 127.0.0.1:8099        # or checklists-bridge:8099
}
```

No base-path rewriting. The watch talks to the same origin as the browser.

## Configuration

| Variable | Required | Default | Purpose |
| --- | --- | --- | --- |
| `CHECKLISTS_ADMIN_PASSWORD` | yes | — | Password for the web UI |
| `CHECKLISTS_DATA_FILE` | no | `data/bridge.json` (`/data/bridge.json` in the image) | State file |
| `CHECKLISTS_PUBLIC_URL` | no | — | The HTTPS URL the watch uses; shown on the pairing screen |
| `CHECKLISTS_HOST` | no | `127.0.0.1` (`0.0.0.0` in the image) | Bind address |
| `CHECKLISTS_PORT` | no | `8099` | Bind port |
| `CHECKLISTS_TRUSTED_PROXIES` | no | `127.0.0.1` (trust nobody but the immediate peer) | IPs/CIDRs, comma-separated, whose `X-Forwarded-*` headers to believe |

The bridge refuses to start without `CHECKLISTS_ADMIN_PASSWORD`.

Relative paths (like the default `CHECKLISTS_DATA_FILE`) resolve against the
working directory the process starts in; the file itself is created
automatically on first save, but its parent directory must already exist.

Behind a reverse proxy, set `CHECKLISTS_TRUSTED_PROXIES` to that proxy's real
address, or the login throttle and the cookie's scheme end up keyed on
whatever peer address the proxy hop presents — the Docker gateway, for a
containerized proxy, not the browser. Find it with
`docker network inspect <project>_default | grep Gateway` once the stack is
up; addresses in that range are usually stable afterwards. The Docker default
bridge range, `172.16.0.0/12`, is a broad starting point if you would rather
not look it up, and is still far narrower than trusting every peer.

## State and backups

One JSON file holds everything: device token, signing secret, provider
credentials, selection, local checklists and the snapshot. Writes are atomic,
so copying it is a valid backup.

```bash
docker compose cp bridge:/data/bridge.json ./bridge-backup.json
```

It contains secrets. Keep it at mode `0600`.

Upgrade with `docker compose up -d --build`; the volume is untouched.

**Bind mounts:** the image owns `/data` as uid 10001, which a *named* volume
inherits and a bind mount does not. `chown 10001:10001` the directory, or add
`user: "$(id -u):$(id -g)"`.

## Without Docker

```bash
just install
export CHECKLISTS_ADMIN_PASSWORD='something long'
just run
```

<details>
<summary>systemd unit</summary>

```ini
[Unit]
Description=Checklists bridge
After=network-online.target

[Service]
User=checklists
WorkingDirectory=/opt/checklists/bridge
Environment=CHECKLISTS_ADMIN_PASSWORD=...
Environment=CHECKLISTS_PUBLIC_URL=https://checklists.example.com
Environment=CHECKLISTS_DATA_FILE=/var/lib/checklists/bridge.json
Environment=CHECKLISTS_TRUSTED_PROXIES=127.0.0.1
ExecStart=/usr/local/bin/uv run checklists-bridge
Restart=on-failure

[Install]
WantedBy=multi-user.target
```
</details>

## HTTP surface

Watch — needs `Authorization: Bearer <device token>`:

| Method | Path | Returns |
| --- | --- | --- |
| GET | `/api/v1/watch/lists?refresh=true` | `{"v":1,"t":…,"l":[{"id","n","c"}]}` |
| GET | `/api/v1/watch/lists/{id}` | `{"id","n","i":[…]}` |

Browser — needs the session cookie: `/api/v1/admin/…`. `GET /healthz` is open.

Keys are single letters to keep the watch's JSON parse small.

## Device token rotation

**New device token** on the web page. The old one stops working immediately.

Then rebuild the watch app, or retype the token in Garmin Connect. Every watch
loses access at once — see below.

## Multiple phones and watches

One bridge is one account, not one device. Everything is shared: the providers,
the checklists, the snapshot.

| To add | Do this |
| --- | --- |
| Another phone | Open the same URL, sign in with the same password. |
| Another watch | Bake in the same device token, or type it in. |

No per-device setup, no limit. A list you edit on one phone is on the other's
next load.

Two things to know before you hand out the password:

- **Rotating the token breaks every watch**, not one. Rebuild them all.
- **You cannot sign out a single phone.** The session cookie proves only that
  somebody knew the password, so one browser cannot be told from another.
  **Sign out everywhere** on the web page is the remedy: it signs out every
  phone at once, this one included. Use it after changing the password, which on
  its own does not end existing sessions.

Want separate people with separate checklists? Run a second bridge: its own data
file, its own port, its own subdomain. One snapshot per bridge, so there is no
way to split one.

## Upgrading

The shipped compose file builds from source. To track the published images
instead (amd64 and arm64, one per release), replace `build: ./bridge` with:

```yaml
    image: ghcr.io/OWNER/REPO:1
```

Pin the major — `:0` while the version is still 0.x, `:1` after that — and you
get fixes without surprises; `:latest` follows every release, major ones
included. Then:

```bash
docker compose pull && docker compose up -d
```

Back up `bridge.json` first. There is only one data schema so far, so nothing
migrates yet; when that changes the bridge will convert the file on first start.
Downgrading is not supported — an older bridge refuses a file a newer one wrote,
rather than quietly mangling it.
