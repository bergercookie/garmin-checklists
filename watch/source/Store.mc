import Toybox.Application;
import Toybox.Lang;
import Toybox.Time;

//! Everything the watch remembers between runs.
//!
//! Tick state lives here and only here: the bridge is a read-only source of
//! checklist templates, so a sync deliberately throws every tick away.
//!
//! One stored checklist looks like:
//!   { "id" => "vikunja:12", "n" => "Dive kit",
//!     "i" => ["Mask", "Fins"], "d" => [false, true] }
//! Keys are single letters because this dictionary is written to persistent
//! storage every time the user ticks something.
//!
//! The watch-side preferences -- whether the clock is shown, and whether the
//! hourly background sync is on -- live here too. Neither is checklist data,
//! so a sync leaves them alone.
//!
//! Annotated for the background process: AutoSyncService calls savePending,
//! and AutoSync.mc reads autoSync from both the foreground and the background.
//! The background never writes KEY_LISTS: the foreground reads, edits and
//! rewrites that array on every tick, and a second writer would race it.
(:background)
module Store {

    const KEY_LISTS = "lists";
    const KEY_SYNCED_AT = "syncedAt";
    const KEY_SHOW_CLOCK = "showClock";
    const KEY_AUTO_SYNC = "autoSync";
    //! A complete background fetch waiting to be applied:
    //!   { "t" => <epoch seconds fetched>, "l" => <what SyncTask collected> }
    const KEY_PENDING = "pending";
    const KEY_LAST_CHECKLIST = "lastChecklist";

    //! All checklists, in the order the bridge sent them.
    function checklists() as Array<Dictionary> {
        var stored = Storage.getValue(KEY_LISTS);
        return stored instanceof Array ? stored as Array<Dictionary> : [] as Array<Dictionary>;
    }

    function count() as Number {
        return checklists().size();
    }

    //! Return one checklist, or null if the index is stale.
    function checklistAt(listIndex as Number) as Dictionary? {
        var all = checklists();
        if (listIndex < 0 || listIndex >= all.size()) {
            return null;
        }
        return all[listIndex];
    }

    //! Replace every checklist. Ticks reset because the items may have changed
    //! and a half-applied tick would be worse than a clean slate.
    function replaceAll(fetched as Array<Dictionary>) as Void {
        replaceAllAt(fetched, Time.now().value());
    }

    //! replaceAll, recording when the lists were actually fetched.
    function replaceAllAt(fetched as Array<Dictionary>, fetchedAt as Number) as Void {
        var stored = [] as Array<Dictionary>;
        for (var index = 0; index < fetched.size(); index += 1) {
            var source = fetched[index];
            // Checked rather than cast: `as` is a compile-time assertion only,
            // and this runs on the path that is about to overwrite good data.
            // A reply missing "i" used to crash here, after the point of no
            // return.
            if (!(source instanceof Dictionary)) {
                continue;
            }
            var id = source["id"];
            var name = source["n"];
            var items = source["i"];
            if (!(id instanceof String) || !(name instanceof String)
                || !(items instanceof Array)) {
                continue;
            }
            var entry = {} as Dictionary;
            entry.put("id", id);
            entry.put("n", name);
            entry.put("i", items);
            entry.put("d", unticked(items.size()));
            stored.add(entry);
        }
        Storage.setValue(KEY_LISTS, stored as Application.Storage.ValueType);
        Storage.setValue(KEY_SYNCED_AT, fetchedAt);
        // Any parked background fetch is this one or older than it.
        Storage.deleteValue(KEY_PENDING);
        // A stored index is only meaningful against the checklists it was
        // recorded with; this fetch may have reordered or removed the one it
        // pointed at.
        Storage.deleteValue(KEY_LAST_CHECKLIST);
    }

    //! Background process only: park a complete fetch for the app to apply.
    //! Throws if storage is full, or on a device where the background process
    //! may not write storage (before Connect IQ 3.2).
    function savePending(fetched as Array<Dictionary>) as Void {
        var pending = { "t" => Time.now().value(), "l" => fetched };
        Storage.setValue(KEY_PENDING, pending as Application.Storage.ValueType);
    }

    //! Apply a parked background fetch, if there is one, exactly as a manual
    //! sync would: every checklist replaced, every tick cleared. Returns true
    //! if it did. Foreground only, and only where no menu built from the old
    //! lists is open.
    function applyPending() as Boolean {
        var pending = Storage.getValue(KEY_PENDING);
        if (!(pending instanceof Dictionary)) {
            return false;
        }
        var fetchedAt = pending["t"];
        var lists = pending["l"];
        if (!(fetchedAt instanceof Number) || !(lists instanceof Array)) {
            Storage.deleteValue(KEY_PENDING);
            return false;
        }
        replaceAllAt(lists as Array<Dictionary>, fetchedAt);
        return true;
    }

    //! Record one item as ticked or unticked.
    function setTicked(listIndex as Number, itemIndex as Number, ticked as Boolean) as Void {
        var all = checklists();
        if (listIndex < 0 || listIndex >= all.size()) {
            return;
        }
        var checklist = all[listIndex] as Dictionary;
        var done = checklist["d"] as Array<Boolean>;
        if (itemIndex < 0 || itemIndex >= done.size()) {
            return;
        }
        done[itemIndex] = ticked;
        checklist.put("d", done);
        all[listIndex] = checklist;
        Storage.setValue(KEY_LISTS, all as Application.Storage.ValueType);
    }

    //! Untick everything in one checklist, ready for the next time it is used.
    function clearTicks(listIndex as Number) as Void {
        var all = checklists();
        if (listIndex < 0 || listIndex >= all.size()) {
            return;
        }
        var checklist = all[listIndex] as Dictionary;
        var items = checklist["i"] as Array<String>;
        checklist.put("d", unticked(items.size()));
        all[listIndex] = checklist;
        Storage.setValue(KEY_LISTS, all as Application.Storage.ValueType);
    }

    //! Seconds since the epoch of the last successful sync, or null.
    function syncedAt() as Number? {
        var value = Storage.getValue(KEY_SYNCED_AT);
        return value instanceof Number ? value : null;
    }

    //! Whether the time is drawn at the top of each screen. On until the user
    //! turns it off in the watch's own Settings menu.
    function showClock() as Boolean {
        var value = Storage.getValue(KEY_SHOW_CLOCK);
        return value instanceof Boolean ? value : true;
    }

    function setShowClock(show as Boolean) as Void {
        Storage.setValue(KEY_SHOW_CLOCK, show);
    }

    //! Whether the hourly background sync is switched on. Off until the user
    //! turns it on in the watch's own Settings menu, because every sync
    //! clears every tick. Read from the background process too (AutoSync.mc).
    function autoSync() as Boolean {
        var value = Storage.getValue(KEY_AUTO_SYNC);
        return value instanceof Boolean ? value : false;
    }

    function setAutoSync(enabled as Boolean) as Void {
        Storage.setValue(KEY_AUTO_SYNC, enabled);
    }

    //! The checklist last opened from the index, so the app can return
    //! straight to it next time. Null once there is none, or none still valid.
    function lastChecklistIndex() as Number? {
        var value = Storage.getValue(KEY_LAST_CHECKLIST);
        if (!(value instanceof Number) || checklistAt(value) == null) {
            return null;
        }
        return value;
    }

    function setLastChecklistIndex(listIndex as Number) as Void {
        Storage.setValue(KEY_LAST_CHECKLIST, listIndex);
    }

    //! Whether a checklist has at least one item ticked. Opening the app
    //! itself skips past the home screen only for a checklist that qualifies
    //! here -- merely having looked at one is not "in progress".
    function hasProgress(listIndex as Number) as Boolean {
        var checklist = checklistAt(listIndex);
        if (checklist == null) {
            return false;
        }
        return (checklist["d"] as Array<Boolean>).indexOf(true) >= 0;
    }

    function unticked(size as Number) as Array<Boolean> {
        var done = [] as Array<Boolean>;
        for (var index = 0; index < size; index += 1) {
            done.add(false);
        }
        return done;
    }
}
