import Toybox.Lang;
import Toybox.WatchUi;

//! The list of checklists, with each one's progress.
//!
//! Built fresh from storage every time it is opened, so a sync is always
//! reflected. Ticking happens in the child view and leaves this one on the
//! stack, so the rows are rebuilt again in onShow on the way back.
module IndexMenu {

    //! Identifiers of the trailing "Sync now" and "Settings" rows; the checklist
    //! rows use their index in storage.
    const SYNC = :sync;
    const SETTINGS = :settings;

    //! Open the index over the home screen.
    function push(main as MainDelegate) as Void {
        var view = new IndexView();
        WatchUi.pushView(view, new IndexMenuDelegate(view, main), WatchUi.SLIDE_LEFT);
    }

    function rows() as Array<MenuRow> {
        var result = [] as Array<MenuRow>;
        var all = Store.checklists();
        for (var index = 0; index < all.size(); index += 1) {
            var checklist = all[index] as Dictionary;
            result.add(new MenuRow(index, checklist["n"] as String, progressLabel(checklist), null));
        }
        result.add(new MenuRow(SYNC, WatchUi.loadResource(Rez.Strings.SyncNow) as String, null, null));
        result.add(
            new MenuRow(SETTINGS, WatchUi.loadResource(Rez.Strings.Settings) as String, null, null)
        );
        return result;
    }

    //! Sub-label such as "3/9 done".
    function progressLabel(checklist as Dictionary) as String {
        var done = checklist["d"] as Array<Boolean>;
        var ticked = 0;
        for (var index = 0; index < done.size(); index += 1) {
            if (done[index]) {
                ticked += 1;
            }
        }
        return Lang.format("$1$/$2$ done", [ticked, done.size()]);
    }
}

class IndexView extends ListMenuView {

    function initialize() {
        ListMenuView.initialize(
            WatchUi.loadResource(Rez.Strings.MenuTitle) as String, IndexMenu.rows(), 0
        );
    }

    //! Coming back from a checklist, the ticks have changed underneath us.
    //! This is also where the daily clear is applied, if its time has passed
    //! while the app was open: no screen built from the old ticks is up.
    function onShow() as Void {
        DailyClear.apply();
        setRows(IndexMenu.rows());
    }
}

class IndexMenuDelegate extends ListMenuDelegate {

    private var _main as MainDelegate;

    function initialize(view as IndexView, main as MainDelegate) {
        ListMenuDelegate.initialize(view, main, 1);
        _main = main;
    }

    function choose(index as Number) as Void {
        var row = _view.row(index);
        if (row == null) {
            return;
        }
        var id = row.id;
        if (id instanceof Number) {
            Store.setLastChecklistIndex(id);
            ItemsMenu.push(id, _main);
        } else if (id == IndexMenu.SETTINGS) {
            SettingsMenu.push(_main);
        } else {
            _main.syncFromMenu(1);
        }
    }
}
