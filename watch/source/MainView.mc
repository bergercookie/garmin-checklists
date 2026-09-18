import Toybox.Graphics;
import Toybox.Lang;
import Toybox.Time;
import Toybox.WatchUi;

//! Home screen: how many checklists are on the watch, when they last came in,
//! and the result of the most recent sync. The time sits at the top unless it
//! has been switched off in Settings.
class MainView extends WatchUi.View {

    private var _message as String?;
    private var _shown as Boolean;
    private var _onShow as Lang.Method or Null;

    function initialize() {
        View.initialize();
        _message = null;
        _shown = false;
        _onShow = null;
    }

    //! Called with no arguments each time this view comes back on top.
    function setOnShow(callback as Lang.Method) as Void {
        _onShow = callback;
    }

    //! True while this is the view on screen, rather than a menu over it.
    function isShown() as Boolean {
        return _shown;
    }

    function onShow() as Void {
        _shown = true;
        var callback = _onShow;
        if (callback != null) {
            callback.invoke();
        }
    }

    function onHide() as Void {
        _shown = false;
    }

    //! Show a short status line, e.g. the outcome of a sync.
    function setMessage(message as String?) as Void {
        _message = message;
        WatchUi.requestUpdate();
    }

    //! Four centred lines. The block is sized from the device's own font
    //! metrics and kept in the middle band of the screen, so it fits a small
    //! round Descent as well as a Fenix 7X without per-device layouts.
    function onUpdate(dc as Graphics.Dc) as Void {
        dc.setColor(Graphics.COLOR_WHITE, Graphics.COLOR_BLACK);
        dc.clear();

        var centreX = dc.getWidth() / 2;
        var titleHeight = dc.getFontHeight(Graphics.FONT_SMALL);
        var lineHeight = dc.getFontHeight(Graphics.FONT_XTINY);
        var blockHeight = titleHeight + (lineHeight * 3);
        var y = ((dc.getHeight() - blockHeight) / 2) + (titleHeight / 2);

        drawLine(dc, centreX, y, Graphics.FONT_SMALL, title());
        y += (titleHeight / 2) + (lineHeight / 2);
        drawLine(dc, centreX, y, Graphics.FONT_XTINY, countLabel());
        y += lineHeight;
        drawLine(dc, centreX, y, Graphics.FONT_XTINY, syncLabel());
        y += lineHeight;
        drawLine(dc, centreX, y, Graphics.FONT_XTINY, footer());

        // Centred one line-height down from the top edge: far enough in to
        // clear the bezel on a round screen, and well above the centred block.
        if (Store.showClock()) {
            drawLine(dc, centreX, lineHeight, Graphics.FONT_XTINY, Clock.label());
        }
    }

    private function drawLine(
        dc as Graphics.Dc, x as Number, y as Number, font as Graphics.FontType, text as String
    ) as Void {
        dc.drawText(
            x, y, font, text, Graphics.TEXT_JUSTIFY_CENTER | Graphics.TEXT_JUSTIFY_VCENTER
        );
    }

    //! The sync result if there is one, otherwise the key hint.
    private function footer() as String {
        var message = _message;
        if (message != null) {
            return message;
        }
        return WatchUi.loadResource(Rez.Strings.HintKeys) as String;
    }

    private function title() as String {
        return WatchUi.loadResource(Rez.Strings.MenuTitle) as String;
    }

    private function countLabel() as String {
        var count = Store.count();
        if (count == 0) {
            return WatchUi.loadResource(Rez.Strings.NoChecklists) as String;
        }
        return Lang.format("$1$ checklists", [count]);
    }

    private function syncLabel() as String {
        var at = Store.syncedAt();
        if (at == null) {
            return WatchUi.loadResource(Rez.Strings.NeverSynced) as String;
        }
        // FORMAT_SHORT gives numeric fields; the declared type is a union
        // because the longer formats return names, hence the casts.
        var moment = Time.Gregorian.info(new Time.Moment(at), Time.FORMAT_SHORT);
        return Lang.format("$1$/$2$ $3$:$4$", [
            (moment.day as Number).format("%d"),
            (moment.month as Number).format("%d"),
            moment.hour.format("%02d"),
            moment.min.format("%02d")
        ]);
    }
}
