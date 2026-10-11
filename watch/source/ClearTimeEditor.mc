import Toybox.Graphics;
import Toybox.Lang;
import Toybox.WatchUi;

//! Sets the daily clear's time of day: the hour, then the minute.
//!
//! A View of its own rather than WatchUi.Picker, for two reasons: a Picker's
//! delegate never sees the MENU key, so "sync from any screen" would have a
//! hole here, and in the simulator its background comes out white under the
//! white text, whatever onUpdate clears first.
//!
//! UP and DOWN change the highlighted field, START moves on and then saves,
//! BACK abandons the change. Hours run 00-23 and minutes go in steps of five,
//! so it reads the same as DailyClear.label.
class ClearTimeView extends WatchUi.View {

    const MINUTE_STEP = 5;

    private var _hour as Number;
    private var _minute as Number;
    //! False while the hour is being set, true while the minute is.
    private var _onMinute as Boolean;

    function initialize(atMinutes as Number) {
        View.initialize();
        _hour = atMinutes / 60;
        // Rounded down to the step; only values set here are ever stored, so
        // this changes nothing in practice.
        _minute = ((atMinutes % 60) / MINUTE_STEP) * MINUTE_STEP;
        _onMinute = false;
    }

    function onMinute() as Boolean {
        return _onMinute;
    }

    function minutesAfterMidnight() as Number {
        return (_hour * 60) + _minute;
    }

    //! Move to the minute field.
    function next() as Void {
        _onMinute = true;
        WatchUi.requestUpdate();
    }

    //! Change the highlighted field by one step, wrapping round.
    function change(direction as Number) as Void {
        if (_onMinute) {
            _minute = (_minute + (direction * MINUTE_STEP) + 60) % 60;
        } else {
            _hour = (_hour + direction + 24) % 24;
        }
        WatchUi.requestUpdate();
    }

    function onUpdate(dc as Graphics.Dc) as Void {
        dc.setColor(Graphics.COLOR_WHITE, Graphics.COLOR_BLACK);
        dc.clear();

        var centreX = dc.getWidth() / 2;
        var tiny = dc.getFontHeight(Graphics.FONT_XTINY);
        var small = dc.getFontHeight(Graphics.FONT_SMALL);
        var number = dc.getFontHeight(Graphics.FONT_NUMBER_MEDIUM);

        if (Store.showClock()) {
            drawText(dc, centreX, tiny, Graphics.FONT_XTINY, Clock.label(), Graphics.COLOR_WHITE);
        }
        drawText(
            dc, centreX, (tiny * 2) + (small / 2), Graphics.FONT_SMALL,
            WatchUi.loadResource(Rez.Strings.ClearAtTitle) as String, Graphics.COLOR_WHITE
        );

        // "HH : MM", the field being set in white and the other one dimmed.
        var middle = dc.getHeight() / 2;
        var gap = dc.getTextWidthInPixels(":", Graphics.FONT_NUMBER_MEDIUM);
        var half = dc.getTextWidthInPixels("00", Graphics.FONT_NUMBER_MEDIUM);
        var hourX = centreX - (gap / 2) - (half / 2) - 4;
        var minuteX = centreX + (gap / 2) + (half / 2) + 4;
        drawText(
            dc, hourX, middle, Graphics.FONT_NUMBER_MEDIUM, _hour.format("%02d"),
            _onMinute ? Graphics.COLOR_LT_GRAY : Graphics.COLOR_WHITE
        );
        drawText(dc, centreX, middle, Graphics.FONT_NUMBER_MEDIUM, ":", Graphics.COLOR_LT_GRAY);
        drawText(
            dc, minuteX, middle, Graphics.FONT_NUMBER_MEDIUM, _minute.format("%02d"),
            _onMinute ? Graphics.COLOR_WHITE : Graphics.COLOR_LT_GRAY
        );
        // An underline marks the field the buttons change.
        var underlineX = _onMinute ? minuteX : hourX;
        dc.setColor(Graphics.COLOR_WHITE, Graphics.COLOR_TRANSPARENT);
        dc.fillRectangle(underlineX - (half / 2), middle + (number / 2) + 2, half, 3);

        drawText(
            dc, centreX, dc.getHeight() - (tiny * 3), Graphics.FONT_XTINY,
            WatchUi.loadResource(_onMinute ? Rez.Strings.ClearAtSave : Rez.Strings.ClearAtNext)
                as String,
            Graphics.COLOR_LT_GRAY
        );
    }

    private function drawText(
        dc as Graphics.Dc, x as Number, y as Number, font as Graphics.FontType, text as String,
        color as Number
    ) as Void {
        dc.setColor(color, Graphics.COLOR_TRANSPARENT);
        dc.drawText(x, y, font, text, Graphics.TEXT_JUSTIFY_CENTER | Graphics.TEXT_JUSTIFY_VCENTER);
    }
}

//! Input for the editor. MENU syncs from here too, like every other screen.
class ClearTimeDelegate extends WatchUi.BehaviorDelegate {

    private var _view as ClearTimeView;
    private var _main as MainDelegate;
    private var _onSaved as Lang.Method;

    function initialize(view as ClearTimeView, main as MainDelegate, onSaved as Lang.Method) {
        BehaviorDelegate.initialize();
        _view = view;
        _main = main;
        _onSaved = onSaved;
    }

    function onNextPage() as Boolean {
        _view.change(-1);
        return true;
    }

    function onPreviousPage() as Boolean {
        _view.change(1);
        return true;
    }

    //! START: on to the minute, then store the time and go back.
    function onSelect() as Boolean {
        if (!_view.onMinute()) {
            _view.next();
            return true;
        }
        DailyClear.setMinutes(_view.minutesAfterMidnight());
        _onSaved.invoke();
        WatchUi.popView(WatchUi.SLIDE_RIGHT);
        return true;
    }

    function onBack() as Boolean {
        WatchUi.popView(WatchUi.SLIDE_RIGHT);
        return true;
    }

    //! Home, the index, settings, then this.
    function onMenu() as Boolean {
        _main.syncFromMenu(3);
        return true;
    }
}
