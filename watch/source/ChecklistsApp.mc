import Toybox.Application;
import Toybox.Lang;
import Toybox.System;
import Toybox.WatchUi;

//! Entry point. Everything interesting lives in MainView / MainDelegate.
//!
//! Annotated because the background process loads the application class too,
//! to reach getServiceDelegate. getInitialView and the callbacks below only
//! ever run in the foreground, which the platform guarantees and the type
//! checker cannot see; they opt out of its background-scope check, as the SDK
//! documents for this case, rather than dragging the UI into the background.
(:background)
class ChecklistsApp extends Application.AppBase {

    //! Built in getInitialView, which never runs in the background process --
    //! ClockTicker reaches Timer and WatchUi, neither available there. Null
    //! guards on onStart/onStop/clockChanged are what keep this safe even if
    //! the platform calls them in that process too, not just the type check.
    private var _clock as ClockTicker?;

    //! Set once the foreground has built its first view; always null in the
    //! background process, which is how the callbacks below tell them apart.
    private var _main as MainDelegate?;

    function initialize() {
        AppBase.initialize();
        _clock = null;
        _main = null;
    }

    (:typecheck(disableBackgroundCheck))
    function onStart(state as Dictionary?) as Void {
        var clock = _clock;
        if (clock != null) {
            clock.refresh();
        }
    }

    (:typecheck(disableBackgroundCheck))
    function onStop(state as Dictionary?) as Void {
        var clock = _clock;
        if (clock != null) {
            clock.stop();
        }
    }

    //! The clock was switched on or off in the watch's Settings menu.
    (:typecheck(disableBackgroundCheck))
    function clockChanged() as Void {
        var clock = _clock;
        if (clock != null) {
            clock.refresh();
        }
    }

    (:typecheck(disableBackgroundCheck))
    function getInitialView() as [WatchUi.Views] or [WatchUi.Views, WatchUi.InputDelegates] {
        AutoSync.schedule();
        // Nothing is on screen yet, so a parked background sync is safe to
        // apply before the first view reads storage.
        var applied = Store.applyPending();
        var clock = new ClockTicker();
        _clock = clock;
        // onStart, which arms the clock, may already have run and found
        // _clock still null -- refresh() is idempotent, so call it again here
        // rather than depend on onStart/getInitialView ordering.
        clock.refresh();
        var view = new MainView();
        var main = new MainDelegate(view);
        if (applied) {
            main.showAutoSynced();
        }
        _main = main;
        // Skip the home screen itself only for a checklist genuinely in
        // progress -- merely having looked at one last time is not enough to
        // bypass the count/last-sync summary on every launch.
        var lastIndex = Store.lastChecklistIndex();
        if (lastIndex != null && Store.hasProgress(lastIndex)) {
            main.resumeOnLaunch();
        }
        return [view, main];
    }

    function getServiceDelegate() as [System.ServiceDelegate] {
        return [new AutoSyncService()];
    }

    //! The background auto-sync finished while the app was open. The number
    //! it sends is only a wake-up call; the lists are parked in storage.
    //!
    //! A run from while the app was closed is also reported here, after
    //! onStart. Before getInitialView it is ignored, because getInitialView
    //! applies storage itself; after, there is nothing left to apply.
    (:typecheck(disableBackgroundCheck))
    function onBackgroundData(data as Application.PersistableType) as Void {
        var main = _main;
        if (main != null) {
            main.onAutoSync();
        }
    }

    //! The user changed a setting in Garmin Connect.
    (:typecheck(disableBackgroundCheck))
    function onSettingsChanged() as Void {
        if (_main != null) {
            AutoSync.schedule();
        }
        WatchUi.requestUpdate();
    }
}

//! Required by the SDK's generated entry point.
function getApp() as ChecklistsApp {
    return Application.getApp() as ChecklistsApp;
}
