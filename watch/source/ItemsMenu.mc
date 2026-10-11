import Toybox.Lang;
import Toybox.WatchUi;

//! One checklist as a list of boxes. Ticking is watch-local and instant: the
//! bridge is never told, by design.
module ItemsMenu {

    function push(listIndex as Number, main as MainDelegate) as Void {
        var view = build(listIndex);
        WatchUi.pushView(view, new ItemsMenuDelegate(view, listIndex, main), WatchUi.SLIDE_LEFT);
    }

    function build(listIndex as Number) as ListMenuView {
        var checklist = Store.checklistAt(listIndex);
        if (checklist == null) {
            return new ListMenuView(
                WatchUi.loadResource(Rez.Strings.MenuTitle) as String, [] as Array<MenuRow>, 0
            );
        }
        var items = checklist["i"] as Array<String>;
        var done = checklist["d"] as Array<Boolean>;
        var rows = [] as Array<MenuRow>;
        for (var index = 0; index < items.size(); index += 1) {
            var heading = ItemKind.isHeading(checklist, index);
            // A heading has no box: it introduces a linked list, and is not
            // itself something to do.
            var row = new MenuRow(index, items[index], null, heading ? null : done[index]);
            row.depth = ItemKind.depth(checklist, index);
            row.heading = heading;
            rows.add(row);
        }
        // -1 when everything is ticked; the top is then the least surprising
        // place to land.
        var focus = ItemKind.firstUnticked(checklist);
        return new ListMenuView(checklist["n"] as String, rows, focus > 0 ? focus : 0);
    }
}

class ItemsMenuDelegate extends ListMenuDelegate {

    private var _listIndex as Number;

    function initialize(view as ListMenuView, listIndex as Number, main as MainDelegate) {
        // Home, the index, then this list.
        ListMenuDelegate.initialize(view, main, 2);
        _listIndex = listIndex;
    }

    //! Flip the box and persist the new state. Headings have none.
    function choose(index as Number) as Void {
        var row = _view.row(index);
        if (row == null || row.on == null) {
            return;
        }
        var ticked = !(row.on as Boolean);
        row.on = ticked;
        Store.setTicked(_listIndex, row.id as Number, ticked);
        WatchUi.requestUpdate();
    }
}
