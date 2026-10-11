import Toybox.Application;
import Toybox.Application;
import Toybox.Lang;
import Toybox.Time;

//! Unticks every checklist once a day, at a time the user picks on the watch.
//!
//! Done lazily rather than from a background event: whenever the app is about
//! to show lists (launch, the home screen, the index) it asks whether the
//! scheduled time has passed since the last clear, and clears if so. The user
//! cannot tell that apart from a clear at exactly that minute, and it needs no
//! background process, which could not safely rewrite the lists anyway -- see
//! the note on KEY_LISTS in Store.
//!
//! On by default at 03:00 local time. Like the other watch-side preferences it
//! is kept in storage on the watch and never sent to the bridge.
module DailyClear {

    //! 03:00, as minutes after local midnight.
    const DEFAULT_MINUTES = 180;
    const MINUTES_PER_DAY = 1440;
    const SECONDS_PER_DAY = 86400;

    //! Whether the daily clear is switched on.
    function enabled() as Boolean {
        var value = Storage.getValue(Store.KEY_CLEAR_DAILY);
        return value instanceof Boolean ? value : true;
    }

    function setEnabled(on as Boolean) as Void {
        Storage.setValue(Store.KEY_CLEAR_DAILY, on);
        // Turning it on, or moving its time, starts counting from now: a time
        // earlier today must not clear lists the user is partway through.
        restart();
    }

    //! The time of day to clear at, in minutes after local midnight.
    function minutes() as Number {
        var value = Storage.getValue(Store.KEY_CLEAR_AT);
        if (value instanceof Number && value >= 0 && value < MINUTES_PER_DAY) {
            return value;
        }
        return DEFAULT_MINUTES;
    }

    function setMinutes(minutesAfterMidnight as Number) as Void {
        Storage.setValue(Store.KEY_CLEAR_AT, minutesAfterMidnight);
        restart();
    }

    //! "03:00". Always 24-hour, matching the picker the user sets it with.
    function label() as String {
        var total = minutes();
        return (total / 60).format("%02d") + ":" + (total % 60).format("%02d");
    }

    //! Treat the lists as just cleared, as far as the schedule goes.
    function restart() as Void {
        Storage.setValue(Store.KEY_CLEARED_AT, Time.now().value());
    }

    //! The most recent scheduled clear at or before now, as epoch seconds.
    //! Pure, so it can be reasoned about without a clock: todayStart is local
    //! midnight, which is what Time.today() returns.
    function lastDue(now as Number, todayStart as Number, atMinutes as Number) as Number {
        var due = todayStart + (atMinutes * 60);
        if (due > now) {
            due -= SECONDS_PER_DAY;
        }
        return due;
    }

    //! Clear every tick if the scheduled time has passed since the last clear.
    //! Returns true if it did. Foreground only, and only where no menu built
    //! from the old ticks is open -- the same rule as Store.applyPending.
    function apply() as Boolean {
        if (!enabled()) {
            return false;
        }
        var clearedAt = Storage.getValue(Store.KEY_CLEARED_AT);
        var now = Time.now().value();
        if (!(clearedAt instanceof Number)) {
            // First run, or an upgrade: nothing has been cleared yet, and the
            // lists the user has now are not "yesterday's".
            restart();
            return false;
        }
        if (clearedAt >= lastDue(now, Time.today().value(), minutes())) {
            return false;
        }
        Store.clearAllTicks();
        Storage.setValue(Store.KEY_CLEARED_AT, now);
        return true;
    }
}
