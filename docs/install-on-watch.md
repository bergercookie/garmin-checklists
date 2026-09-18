# Installing on a watch

## Copy the `.prg`, not the `.iq`

| File | Built by | What it is |
| --- | --- | --- |
| `checklists-<device>.prg` | `just watch-build` | One device's binary. **This goes on the watch.** |
| `checklists.iq` | `just watch-package` | Multi-device bundle for the Connect IQ store. The watch cannot read it. |

`watch-package` builds every product in the manifest, so it needs each one's
device files installed in the SDK Manager. `watch-build` needs only one.

## Get a usable path

A fenix 7 connects as an MTP device by default, which is why there is no path to
copy to. Either switch it, or use `gio`.

### Option A — mass storage

On the watch: **Settings → System → USB Mode → Garmin**, then *unplug and
replug* (the mode is chosen when the cable connects).

```bash
cp build/checklists-fenix7.prg /media/$USER/GARMIN/GARMIN/APPS/
sync && udisksctl unmount -b /dev/disk/by-label/GARMIN
```

The doubled `GARMIN` is right: `GARMIN/APPS` sits inside a volume called
GARMIN. Mount point varies (`/media/$USER/…`, `/run/media/$USER/…`, `/Volumes/…`).

Nothing appeared? `lsusb | grep -i garmin` and `lsblk -o NAME,LABEL,MOUNTPOINT`.
A disk labelled `GARMIN` means only the automounter is missing —
`udisksctl mount -b /dev/sdX1`. No disk means it is still in MTP mode.

### Option B — stay on MTP

`gio` copies straight to the URI, with no mount point and no `gvfs-fuse`:

```bash
gio mount -li | grep -i mtp
gio copy -p build/checklists-fenix7.prg \
    "mtp://091e_4f43_0000d07eee5a/Internal Storage/GARMIN/APPS/"
gio list "mtp://091e_4f43_0000d07eee5a/Internal Storage/GARMIN/APPS"
```

`091e` is Garmin's vendor id; the rest is your watch's.
`/run/user/$UID/gvfs/` being empty is normal unless the `gvfs-fuse` package is
installed — it is not a sign anything is wrong.

For a real mount point instead: `jmtpfs ~/mnt/watch`.

## After copying

Eject, unplug. The `.prg` **disappears** from `GARMIN/APPS/` — the watch files
it into internal storage. That is normal.

Checklists now appears in the app list, and `GARMIN/APPS/SETTINGS/CHECKLISTS.SET`
appears alongside it.

## The `.SET` file

The watch stores your settings in `GARMIN/APPS/SETTINGS/CHECKLISTS.SET`, and
**stored settings beat anything compiled into the `.prg`**.

```{warning}
Reinstalling with a baked-in URL and token? Delete the `.SET` first, or the
old empty values win and the app still says *Set URL + token*.
```

```bash
gio remove "mtp://<device>/Internal Storage/GARMIN/APPS/SETTINGS/CHECKLISTS.SET"
```

Uninstalling the app from the watch does the same thing.

## If Garmin Connect will not open the settings page

Its settings page can crash — that is a Connect problem, not a malformed
`settings.xml` (these resources validate against the SDK's own `resources.xsd`).
In order:

1. The standalone **Connect IQ** app on the phone — a different code path.
2. **Garmin Express** on a desktop.
3. Compile the pairing in and skip the phone:

```bash
BRIDGE_URL=https://checklists.example.com \
DEVICE_TOKEN=K7QF-2M9X-PLDR \
CIQ_KEY=~/developer_key.der just watch-build
```

Two caveats: the token ends up **inside the `.prg`**, so do not share that
build; and you must delete the `.SET` first, as above. A paired build shows
*Sync failed (…)* rather than *Set URL + token* on first sync — that is how you
know it took.
