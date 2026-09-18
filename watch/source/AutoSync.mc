import Toybox.Background;
import Toybox.Lang;
import Toybox.System;
import Toybox.Time;

//! Optional hourly sync, run by the Connect IQ background service so the
//! checklists are fresh without anyone opening the app to ask.
//!
//! It is the ordinary one-way sync, nothing more: the same two read-only GETs
//! (SyncTask), and the result replaces every checklist and clears every tick
//! (Store.replaceAll). Nothing is sent back to the bridge.
//!
//! The background process only fetches; it never touches the stored
//! checklists. A complete fetch is parked in storage under its own key and the
//! app applies it the next time that is safe -- at start-up, or on the home
//! screen -- because a menu built from the old lists may be open, and its row
//! indices would otherwise point into the new ones.
//!
//! Off by default, because a sync clears ticks: see docs/watch-app.md.
module AutoSync {

    //! One hour. The platform floor is five minutes, but templates change
    //! rarely and every wake costs radio time on the watch and the phone.
    const INTERVAL_SECONDS = 3600;

    //! Register or remove the temporal event to match the settings. Called
    //! from the foreground whenever the app starts or its settings change.
    //!
    //! An existing registration with the same interval is left alone: calling
    //! registerForTemporalEvent again would restart the hour, and a user who
    //! opens the app more often than hourly would never get a background sync.
    function schedule() as Void {
        if (!(Toybox has :Background)) {
            return;
        }
        var registered = Background.getTemporalEventRegisteredTime();
        if (!Store.autoSync() || !AppConfig.isReady()) {
            if (registered != null) {
                Background.deleteTemporalEvent();
            }
            return;
        }
        if (registered instanceof Time.Duration) {
            if (registered.value() == INTERVAL_SECONDS) {
                return;
            }
        }
        Background.registerForTemporalEvent(new Time.Duration(INTERVAL_SECONDS));
    }
}

//! The background half: runs SyncTask and parks a complete result.
//!
//! Everything reachable from here must carry the (:background) annotation --
//! SyncTask, AppConfig and Store do -- and must stay small: the background
//! heap is 64 KB on the fenix 7 family and the Descent G2, code included.
(:background)
class AutoSyncService extends System.ServiceDelegate {

    //! Held so the task, and the callbacks it has handed to Communications,
    //! outlive onTemporalEvent.
    private var _task as SyncTask?;

    function initialize() {
        ServiceDelegate.initialize();
        _task = null;
    }

    //! The setting is read again here, not trusted from scheduling time: an
    //! event already queued by the platform can still fire the moment after
    //! Settings switches this off and schedule() calls deleteTemporalEvent.
    function onTemporalEvent() as Void {
        if (!Store.autoSync()) {
            Background.exit(null);
            return;
        }
        _task = new SyncTask(method(:onSyncDone), true);
        (_task as SyncTask).start();
    }

    //! A failure is simply dropped: there is no screen to show it on, and the
    //! next attempt is an hour away. The home screen's "last synced" time is
    //! how the user notices that auto-sync is not getting through.
    function onSyncDone(status as Number, lists as Array<Dictionary>) as Void {
        _task = null;
        var outcome = status;
        if (status == SyncTask.OK) {
            try {
                Store.savePending(lists);
            } catch (error) {
                // StorageFullException, or ObjectStoreAccessException on a
                // device older than Connect IQ 3.2, where the background
                // process may not write storage at all.
                outcome = SyncTask.BAD_RESPONSE;
            }
        }
        // The number is only a wake-up call for a running app; the lists
        // themselves travel through storage, which has no 8 KB ceiling.
        Background.exit(outcome);
    }
}
