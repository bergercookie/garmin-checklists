import Toybox.Graphics;
import Toybox.Lang;
import Toybox.WatchUi;

//! Why the app's lists are drawn here and not with WatchUi.Menu2: a Menu2 is
//! driven by firmware and hands its delegate only select/back/title events.
//! The MENU key (long-press UP) never reaches it -- confirmed in the real
//! simulator, with a BehaviorDelegate and with onKey as well -- so no Menu2
//! screen could offer "sync from here". A plain View with a BehaviorDelegate
//! does receive it, on every screen.

//! One line of a list: a label, an optional second line, and an optional
//! on/off box on the right.
class MenuRow {

    //! What the screen's delegate uses to tell rows apart.
    var id as Object;
    var label as String;
    var sub as String?;
    //! Null for a row with no box.
    var on as Boolean?;

    function initialize(id as Object, label as String, sub as String?, on as Boolean?) {
        self.id = id;
        self.label = label;
        self.sub = sub;
        self.on = on;
    }
}

//! A titled, scrolling list with one focused row, in the manner of a Menu2.
//!
//! Sized from the device's own font metrics, so one layout serves the round
//! Fenix 7 family and the Descent G2. The time sits above the title while the
//! clock is on, as on the home screen.
class ListMenuView extends WatchUi.View {

    private var _title as String;
    private var _rows as Array<MenuRow>;
    private var _focus as Number;
    //! First row in view; moved just far enough to keep the focus visible.
    private var _top as Number;
    //! Layout from the last draw, so a tap can be mapped back to a row.
    private var _rowsFrom as Number;
    private var _rowHeight as Number;
    private var _visible as Number;

    function initialize(title as String, rows as Array<MenuRow>, focus as Number) {
        View.initialize();
        _title = title;
        _rows = rows;
        _focus = focus;
        _top = 0;
        _rowsFrom = 0;
        _rowHeight = 1;
        _visible = 1;
    }

    function size() as Number {
        return _rows.size();
    }

    function row(index as Number) as MenuRow? {
        if (index < 0 || index >= _rows.size()) {
            return null;
        }
        return _rows[index];
    }

    function focus() as Number {
        return _focus;
    }

    function setRows(rows as Array<MenuRow>) as Void {
        _rows = rows;
        if (_focus >= rows.size()) {
            _focus = rows.size() > 0 ? rows.size() - 1 : 0;
        }
        WatchUi.requestUpdate();
    }

    function setFocus(index as Number) as Void {
        if (index >= 0 && index < _rows.size()) {
            _focus = index;
            WatchUi.requestUpdate();
        }
    }

    //! Move the focus by delta rows, stopping at either end.
    function move(delta as Number) as Void {
        setFocus(_focus + delta);
    }

    //! The row drawn at screen height y from the last draw, or -1.
    function rowAt(y as Number) as Number {
        if (y < _rowsFrom) {
            return -1;
        }
        var index = _top + ((y - _rowsFrom) / _rowHeight);
        if (index < _top || index >= _top + _visible || index >= _rows.size()) {
            return -1;
        }
        return index;
    }

    function onUpdate(dc as Graphics.Dc) as Void {
        dc.setColor(Graphics.COLOR_WHITE, Graphics.COLOR_BLACK);
        dc.clear();

        var width = dc.getWidth();
        var height = dc.getHeight();
        var small = dc.getFontHeight(Graphics.FONT_SMALL);
        var tiny = dc.getFontHeight(Graphics.FONT_XTINY);

        // Header, laid out as on the home screen: the time one line down from
        // the top edge, the title under it.
        if (Store.showClock()) {
            drawCentred(dc, width / 2, tiny, Graphics.FONT_XTINY, Clock.label());
        }
        var titleY = (tiny * 2) + (small / 2);
        drawCentred(dc, width / 2, titleY, Graphics.FONT_SMALL, fit(dc, _title, Graphics.FONT_SMALL, (width * 3) / 4));

        // Rows fill what is left, clear of the bezel at the bottom.
        var from = titleY + (small / 2) + (tiny / 4);
        var bottom = height - (height / 8);
        var rowHeight = small + 6;
        for (var index = 0; index < _rows.size(); index += 1) {
            if (_rows[index].sub != null) {
                rowHeight = small + tiny + 6;
                break;
            }
        }
        var visible = (bottom - from) / rowHeight;
        if (visible < 1) {
            visible = 1;
        }
        if (_focus < _top) {
            _top = _focus;
        } else if (_focus >= _top + visible) {
            _top = _focus - visible + 1;
        }
        _rowsFrom = from;
        _rowHeight = rowHeight;
        _visible = visible;

        var inset = width / 7;
        var box = tiny;
        for (var slot = 0; slot < visible && _top + slot < _rows.size(); slot += 1) {
            drawRow(dc, _rows[_top + slot], _top + slot == _focus, from + (slot * rowHeight),
                rowHeight, inset, box, small, tiny);
        }
        drawScrollbar(dc, width - (inset / 2), from, visible * rowHeight, visible);
    }

    private function drawRow(
        dc as Graphics.Dc, row as MenuRow, focused as Boolean, y as Number, rowHeight as Number,
        inset as Number, box as Number, small as Number, tiny as Number
    ) as Void {
        var width = dc.getWidth();
        var textRoom = width - (2 * inset) - (row.on != null ? box + 8 : 0);
        var middle = y + (rowHeight / 2);
        var sub = row.sub;

        if (focused) {
            dc.setColor(Graphics.COLOR_WHITE, Graphics.COLOR_TRANSPARENT);
            dc.fillRectangle(inset - 8, y + 3, 3, rowHeight - 6);
        }
        dc.setColor(
            focused ? Graphics.COLOR_WHITE : Graphics.COLOR_LT_GRAY, Graphics.COLOR_TRANSPARENT
        );
        var labelY = sub == null ? middle : middle - (tiny / 2);
        dc.drawText(
            inset, labelY, Graphics.FONT_SMALL, fit(dc, row.label, Graphics.FONT_SMALL, textRoom),
            Graphics.TEXT_JUSTIFY_LEFT | Graphics.TEXT_JUSTIFY_VCENTER
        );
        if (sub != null) {
            dc.setColor(Graphics.COLOR_LT_GRAY, Graphics.COLOR_TRANSPARENT);
            dc.drawText(
                inset, middle + (small / 2), Graphics.FONT_XTINY,
                fit(dc, sub, Graphics.FONT_XTINY, textRoom),
                Graphics.TEXT_JUSTIFY_LEFT | Graphics.TEXT_JUSTIFY_VCENTER
            );
        }

        var on = row.on;
        if (on != null) {
            var left = width - inset - box;
            var top = middle - (box / 2);
            if (on) {
                dc.setColor(Graphics.COLOR_GREEN, Graphics.COLOR_TRANSPARENT);
                dc.fillRoundedRectangle(left, top, box, box, 3);
            } else {
                dc.setColor(Graphics.COLOR_LT_GRAY, Graphics.COLOR_TRANSPARENT);
                dc.drawRoundedRectangle(left, top, box, box, 3);
            }
        }
    }

    //! A thin bar at the right edge, only when there is more than fits.
    private function drawScrollbar(
        dc as Graphics.Dc, x as Number, y as Number, room as Number, visible as Number
    ) as Void {
        var total = _rows.size();
        if (total <= visible) {
            return;
        }
        dc.setColor(Graphics.COLOR_DK_GRAY, Graphics.COLOR_TRANSPARENT);
        dc.fillRectangle(x, y, 3, room);
        dc.setColor(Graphics.COLOR_WHITE, Graphics.COLOR_TRANSPARENT);
        dc.fillRectangle(x, y + ((room * _top) / total), 3, (room * visible) / total);
    }

    private function drawCentred(
        dc as Graphics.Dc, x as Number, y as Number, font as Graphics.FontType, text as String
    ) as Void {
        dc.setColor(Graphics.COLOR_WHITE, Graphics.COLOR_TRANSPARENT);
        dc.drawText(x, y, font, text, Graphics.TEXT_JUSTIFY_CENTER | Graphics.TEXT_JUSTIFY_VCENTER);
    }

    //! text, cut short with an ellipsis if it is wider than maxWidth.
    private function fit(
        dc as Graphics.Dc, text as String, font as Graphics.FontType, maxWidth as Number
    ) as String {
        if (dc.getTextWidthInPixels(text, font) <= maxWidth) {
            return text;
        }
        for (var end = text.length() - 1; end > 0; end -= 1) {
            var candidate = AppConfig.slice(text, 0, end) + "…";
            if (dc.getTextWidthInPixels(candidate, font) <= maxWidth) {
                return candidate;
            }
        }
        return "…";
    }
}

//! Input for a ListMenuView: UP and DOWN move the focus, START chooses, BACK
//! returns, and MENU -- long-press UP -- syncs from wherever the user is.
class ListMenuDelegate extends WatchUi.BehaviorDelegate {

    protected var _view as ListMenuView;
    private var _main as MainDelegate;
    //! How many views are stacked above the home screen, this one included.
    private var _depth as Number;

    function initialize(view as ListMenuView, main as MainDelegate, depth as Number) {
        BehaviorDelegate.initialize();
        _view = view;
        _main = main;
        _depth = depth;
    }

    //! What choosing a row does. Overridden by each screen.
    function choose(index as Number) as Void {
    }

    function onNextPage() as Boolean {
        _view.move(1);
        return true;
    }

    function onPreviousPage() as Boolean {
        _view.move(-1);
        return true;
    }

    function onSelect() as Boolean {
        choose(_view.focus());
        return true;
    }

    function onTap(event as WatchUi.ClickEvent) as Boolean {
        var index = _view.rowAt(event.getCoordinates()[1]);
        if (index >= 0) {
            _view.setFocus(index);
            choose(index);
        }
        return true;
    }

    function onBack() as Boolean {
        WatchUi.popView(WatchUi.SLIDE_RIGHT);
        return true;
    }

    //! Sync replaces every checklist, so every screen built from the old ones
    //! is dropped on the way back to the home screen first.
    function onMenu() as Boolean {
        _main.syncFromMenu(_depth);
        return true;
    }
}
