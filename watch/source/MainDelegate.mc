import Toybox.Lang;
import Toybox.WatchUi;

//! Input on the home screen: START opens the checklists, MENU syncs. START
//! also resumes straight into whichever checklist was last opened, and so
//! does app launch itself when that checklist has ticks in progress.
class MainDelegate extends WatchUi.BehaviorDelegate {

    private var _view as MainView;
    private var _task as SyncTask?;
    private var _syncing as Boolean;
    //! A background sync finished while a menu was open; apply it on the way
    //! back to the home screen.
    private var _autoSyncWaiting as Boolean;
    //! Set once, from getInitialView, when app launch itself should resume
    //! straight into a checklist with progress. WatchUi.pushView has no
    //! effect when called from inside getInitialView before it returns --
    //! confirmed in the real simulator, not merely assumed -- so the actual
    //! navigation waits for onHomeShown, the first proof the initial view is
    //! really on screen. Cleared after firing once, so returning to the home
    //! screen later in the same session behaves normally.
    private var _resumeOnLaunch as Boolean;

    function initialize(view as MainView) {
        BehaviorDelegate.initialize();
        _view = view;
        _task = null;
        _syncing = false;
        _autoSyncWaiting = false;
        _resumeOnLaunch = false;
        view.setOnShow(method(:onHomeShown));
    }

    function onSelect() as Boolean {
        if (Store.count() == 0) {
            startSync();
            return true;
        }
        enterChecklists();
        return true;
    }

    //! Push the index and, if a checklist was last opened, its items menu
    //! straight on top of that -- shared by START from home and, when app
    //! launch decides there is progress worth resuming, by getInitialView.
    function enterChecklists() as Void {
        WatchUi.pushView(new IndexMenu(), new IndexMenuDelegate(self), WatchUi.SLIDE_LEFT);
        // The index is still underneath for BACK, and its counts are
        // refreshed in onShow on the way back to it -- this only shortcuts
        // the trip in, not the ability to see or reach anything else.
        var lastIndex = Store.lastChecklistIndex();
        if (lastIndex != null) {
            WatchUi.pushView(
                ItemsMenu.build(lastIndex), new ItemsMenuDelegate(lastIndex), WatchUi.SLIDE_LEFT
            );
        }
    }

    function onMenu() as Boolean {
        startSync();
        return true;
    }

    //! Fetch everything from the bridge, showing a progress bar meanwhile.
    function startSync() as Void {
        if (_syncing) {
            return;
        }
        _syncing = true;
        // This sync replaces everything anyway; a background result that was
        // waiting must not be applied over it when the progress bar closes.
        _autoSyncWaiting = false;
        _view.setMessage(null);
        WatchUi.pushView(
            new WatchUi.ProgressBar(WatchUi.loadResource(Rez.Strings.Syncing) as String, null),
            new SyncProgressDelegate(),
            WatchUi.SLIDE_UP
        );
        _task = new SyncTask(method(:onSyncDone), false);
        (_task as SyncTask).start();
    }

    //! Called once by SyncTask, whatever the outcome.
    function onSyncDone(status as Number, lists as Array<Dictionary>) as Void {
        var message = SyncOutcome.apply(status, lists);
        _syncing = false;
        _task = null;
        WatchUi.popView(WatchUi.SLIDE_DOWN);
        _view.setMessage(message);
    }

    //! The background auto-sync has parked a fresh fetch in storage. Apply it
    //! now if the home screen is showing; deeper in, a menu built from the old
    //! lists is open and its row indices would point into the new ones, so
    //! wait until the user comes back here. During a manual sync, do nothing:
    //! that sync replaces everything and discards the parked copy.
    function onAutoSync() as Void {
        if (_syncing) {
            return;
        }
        if (_view.isShown()) {
            applyAutoSync();
        } else {
            _autoSyncWaiting = true;
        }
    }

    //! Called once, from getInitialView, before the initial view is actually
    //! on screen -- see _resumeOnLaunch.
    function resumeOnLaunch() as Void {
        _resumeOnLaunch = true;
    }

    //! MainView is back on top -- including the very first time, at launch.
    function onHomeShown() as Void {
        if (_resumeOnLaunch) {
            _resumeOnLaunch = false;
            enterChecklists();
            return;
        }
        if (_autoSyncWaiting && !_syncing) {
            _autoSyncWaiting = false;
            applyAutoSync();
        }
    }

    //! Say why the ticks just vanished.
    function showAutoSynced() as Void {
        _view.setMessage(WatchUi.loadResource(Rez.Strings.AutoSyncOk) as String);
    }

    private function applyAutoSync() as Void {
        if (Store.applyPending()) {
            showAutoSynced();
        }
    }
}

//! Keeps BACK from dismissing the progress bar while a sync is in flight; the
//! sync itself always pops it.
class SyncProgressDelegate extends WatchUi.BehaviorDelegate {

    function initialize() {
        BehaviorDelegate.initialize();
    }

    function onBack() as Boolean {
        return true;
    }
}
