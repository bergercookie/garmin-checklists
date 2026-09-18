import Toybox.Graphics;
import Toybox.Lang;
import Toybox.System;
import Toybox.Timer;
import Toybox.WatchUi;

//! The small time-of-day readout at the top of each screen.
//!
//! Menu2 draws its own rows in firmware and cannot be painted over, and a
//! Connect IQ view cannot be layered over another one. What Menu2 does allow is
//! a Drawable in place of its title (API 3.0.0+), so inside the menus the time
//! shares the title area with the menu's own name. The home screen is an
//! ordinary View and draws it directly.
module Clock {

    //! The current time, honouring the watch's 12h/24h setting: "14:05" or
    //! "2:05". No AM/PM, as in the watch's own status readouts.
    function label() as String {
        var now = System.getClockTime();
        var minutes = now.min.format("%02d");
        if (System.getDeviceSettings().is24Hour) {
            return now.hour.format("%02d") + ":" + minutes;
        }
        var hour = now.hour % 12;
        if (hour == 0) {
            hour = 12;
        }
        return hour.format("%d") + ":" + minutes;
    }

    //! A Menu2 title: the plain name when the clock is off, so the menu looks
    //! exactly as it did before, otherwise the name with the time above it.
    function title(name as String) as String or WatchUi.Drawable {
        if (!Store.showClock()) {
            return name;
        }
        return new ClockTitle(name);
    }
}

//! Menu2 title drawable: the time on a small line at the top, the menu's name
//! underneath in the largest font that still leaves room for it.
class ClockTitle extends WatchUi.Drawable {

    private var _name as String;
    //! The name as last fitted, and the font and width it was fitted for; the
    //! title is redrawn on every scroll step, so this is not recomputed each time.
    private var _fitted as String?;
    private var _fittedFont as Graphics.FontDefinition?;
    private var _fittedWidth as Number;

    function initialize(name as String) {
        Drawable.initialize({});
        _name = name;
        _fitted = null;
        _fittedFont = null;
        _fittedWidth = 0;
    }

    function draw(dc as Graphics.Dc) as Void {
        // As in the SDK's own Menu2 sample: the drawable owns its whole area,
        // so clear it, or each minute would be drawn over the last.
        dc.setColor(Graphics.COLOR_BLACK, Graphics.COLOR_BLACK);
        dc.clear();

        var width = dc.getWidth();
        var height = dc.getHeight();
        var timeHeight = dc.getFontHeight(Graphics.FONT_XTINY);
        var nameFont = nameFontFor(dc, height - timeHeight);
        var nameHeight = dc.getFontHeight(nameFont);
        var gap = (height - timeHeight - nameHeight) / 3;
        if (gap < 0) {
            gap = 0;
        }

        dc.setColor(Graphics.COLOR_WHITE, Graphics.COLOR_TRANSPARENT);
        drawCentred(dc, gap + (timeHeight / 2), Graphics.FONT_XTINY, Clock.label());
        // Three quarters of the width keeps the name clear of the bezel on a
        // round screen, where the title area narrows towards the top.
        drawCentred(
            dc, height - gap - (nameHeight / 2), nameFont, fittedName(dc, nameFont, (width * 3) / 4)
        );
    }

    private function drawCentred(
        dc as Graphics.Dc, y as Number, font as Graphics.FontType, text as String
    ) as Void {
        dc.drawText(
            dc.getWidth() / 2, y, font, text,
            Graphics.TEXT_JUSTIFY_CENTER | Graphics.TEXT_JUSTIFY_VCENTER
        );
    }

    private function nameFontFor(dc as Graphics.Dc, room as Number) as Graphics.FontDefinition {
        var fonts = [Graphics.FONT_SMALL, Graphics.FONT_TINY] as Array<Graphics.FontDefinition>;
        for (var index = 0; index < fonts.size(); index += 1) {
            if (dc.getFontHeight(fonts[index]) <= room) {
                return fonts[index];
            }
        }
        return Graphics.FONT_XTINY;
    }

    //! The name, cut short with an ellipsis if it is wider than maxWidth.
    private function fittedName(
        dc as Graphics.Dc, font as Graphics.FontDefinition, maxWidth as Number
    ) as String {
        var cached = _fitted;
        if (cached != null && _fittedFont == font && _fittedWidth == maxWidth) {
            return cached;
        }
        var fitted = "…";
        if (dc.getTextWidthInPixels(_name, font) <= maxWidth) {
            fitted = _name;
        } else {
            for (var end = _name.length() - 1; end > 0; end -= 1) {
                var candidate = AppConfig.slice(_name, 0, end) + "…";
                if (dc.getTextWidthInPixels(candidate, font) <= maxWidth) {
                    fitted = candidate;
                    break;
                }
            }
        }
        _fitted = fitted;
        _fittedFont = font;
        _fittedWidth = maxWidth;
        return fitted;
    }
}

//! Redraws the current screen as each minute turns over, while the clock is on.
//!
//! A one-shot timer re-armed for the next minute boundary, rather than a
//! repeating one, so the readout changes when the minute does and the app is
//! woken once a minute rather than every second. Owned by ChecklistsApp.
class ClockTicker {

    private var _timer as Timer.Timer?;

    function initialize() {
        _timer = null;
    }

    //! Start or stop to match the stored preference.
    function refresh() as Void {
        stop();
        if (Store.showClock()) {
            arm();
        }
    }

    function stop() as Void {
        var timer = _timer;
        if (timer != null) {
            timer.stop();
        }
    }

    function onTick() as Void {
        WatchUi.requestUpdate();
        arm();
    }

    private function arm() as Void {
        var timer = _timer;
        if (timer == null) {
            timer = new Timer.Timer();
            _timer = timer;
        }
        timer.stop();
        var seconds = 60 - System.getClockTime().sec;
        timer.start(method(:onTick), seconds * 1000, false);
    }
}
