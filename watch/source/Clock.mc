import Toybox.Lang;
import Toybox.System;
import Toybox.Timer;
import Toybox.WatchUi;

//! The small time-of-day readout at the top of each screen. Every screen is a
//! plain View (the lists are ListMenuView) and draws it itself, from label().
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
