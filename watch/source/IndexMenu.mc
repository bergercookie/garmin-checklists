import Toybox.Lang;
import Toybox.WatchUi;

//! The list of checklists, with each one's progress.
//!
//! Built fresh from storage every time it is opened, so a sync is always
//! reflected. Ticking happens in the child view and leaves this menu on the
//! stack, so the counts are refreshed again in onShow on the way back.
class IndexMenu extends WatchUi.Menu2 {

    //! Identifiers of the trailing "Sync now" and "Settings" entries.
    static const SYNC = :sync;
    static const SETTINGS = :settings;

    private var _rows as Array<WatchUi.MenuItem>;

    function initialize() {
        Menu2.initialize({
            :title => Clock.title(WatchUi.loadResource(Rez.Strings.MenuTitle) as String)
        });
        _rows = [] as Array<WatchUi.MenuItem>;

        var all = Store.checklists();
        for (var index = 0; index < all.size(); index += 1) {
            var checklist = all[index] as Dictionary;
            var row = new WatchUi.MenuItem(
                checklist["n"] as String, progressLabel(checklist), index, null
            );
            _rows.add(row);
            addItem(row);
        }
        addItem(
            new WatchUi.MenuItem(
                WatchUi.loadResource(Rez.Strings.SyncNow) as String, null, SYNC, null
            )
        );
        addItem(
            new WatchUi.MenuItem(
                WatchUi.loadResource(Rez.Strings.Settings) as String, null, SETTINGS, null
            )
        );
    }

    //! Coming back from a checklist, the ticks have changed underneath us; and
    //! coming back from Settings, the clock may have been switched on or off.
    function onShow() as Void {
        Menu2.onShow();
        setTitle(Clock.title(menuTitle()));
        var all = Store.checklists();
        for (var index = 0; index < _rows.size() && index < all.size(); index += 1) {
            _rows[index].setSubLabel(progressLabel(all[index] as Dictionary));
        }
        WatchUi.requestUpdate();
    }

    private function menuTitle() as String {
        return WatchUi.loadResource(Rez.Strings.MenuTitle) as String;
    }

    //! Sub-label such as "3/9 done".
    private function progressLabel(checklist as Dictionary) as String {
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

class IndexMenuDelegate extends WatchUi.Menu2InputDelegate {

    private var _main as MainDelegate;

    function initialize(main as MainDelegate) {
        Menu2InputDelegate.initialize();
        _main = main;
    }

    function onSelect(item as WatchUi.MenuItem) as Void {
        var id = item.getId();
        if (id instanceof Number) {
            Store.setLastChecklistIndex(id);
            WatchUi.pushView(
                ItemsMenu.build(id), new ItemsMenuDelegate(id), WatchUi.SLIDE_LEFT
            );
            return;
        }
        if (id == IndexMenu.SETTINGS) {
            var settings = SettingsMenu.build();
            WatchUi.pushView(settings, new SettingsMenuDelegate(settings), WatchUi.SLIDE_LEFT);
            return;
        }
        // Syncing replaces every checklist, so drop this menu before starting.
        WatchUi.popView(WatchUi.SLIDE_RIGHT);
        _main.startSync();
    }
}
