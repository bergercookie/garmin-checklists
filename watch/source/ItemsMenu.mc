import Toybox.Lang;
import Toybox.WatchUi;

//! One checklist as a menu of toggles. Ticking is watch-local and instant: the
//! bridge is never told, by design.
module ItemsMenu {

    function build(listIndex as Number) as WatchUi.Menu2 {
        var checklist = Store.checklistAt(listIndex);
        if (checklist == null) {
            return new WatchUi.Menu2({
                :title => Clock.title(WatchUi.loadResource(Rez.Strings.MenuTitle) as String)
            });
        }
        // The checklist's name stays the title; the clock, when on, sits above it.
        var menu = new WatchUi.Menu2({ :title => Clock.title(checklist["n"] as String) });
        var items = checklist["i"] as Array<String>;
        var done = checklist["d"] as Array<Boolean>;
        for (var index = 0; index < items.size(); index += 1) {
            menu.addItem(
                new WatchUi.ToggleMenuItem(items[index], null, index, done[index], null)
            );
        }
        // -1 when everything is ticked; the top is then the least surprising
        // place to land.
        var focus = done.indexOf(false);
        if (focus > 0) {
            menu.setFocus(focus);
        }
        return menu;
    }
}

class ItemsMenuDelegate extends WatchUi.Menu2InputDelegate {

    private var _listIndex as Number;

    function initialize(listIndex as Number) {
        Menu2InputDelegate.initialize();
        _listIndex = listIndex;
    }

    //! The framework has already flipped the toggle; persist the new state.
    function onSelect(item as WatchUi.MenuItem) as Void {
        if (item instanceof WatchUi.ToggleMenuItem) {
            Store.setTicked(_listIndex, item.getId() as Number, item.isEnabled());
        }
    }
}
