import Toybox.Application;
import Toybox.Lang;
import Toybox.Test;
import Toybox.Time;

//! Unit tests for the daily clear. Run with `just watch-test`: they need the
//! simulator, because they use real storage and the real clock, and they leave
//! the simulator's stored checklists in whatever state the last test did.

const MIDNIGHT = 1000000;
const THREE_AM = 180;
const HOUR = 3600;

//! One checklist of three items, the first two ticked.
function seed() as Void {
    Application.Storage.clearValues();
    var lists = [
        { "id" => "t:1", "n" => "Test", "i" => ["a", "b", "c"], "d" => [true, true, false] },
        { "id" => "t:2", "n" => "Other", "i" => ["x"], "d" => [true] }
    ];
    Application.Storage.setValue(Store.KEY_LISTS, lists as Application.Storage.ValueType);
}

function tickedCount() as Number {
    var count = 0;
    var all = Store.checklists();
    for (var index = 0; index < all.size(); index += 1) {
        var done = (all[index] as Dictionary)["d"] as Array<Boolean>;
        for (var item = 0; item < done.size(); item += 1) {
            if (done[item]) {
                count += 1;
            }
        }
    }
    return count;
}

(:test)
function dueIsTodayOnceTheTimeHasPassed(logger as Logger) as Boolean {
    var now = MIDNIGHT + (4 * HOUR);
    Test.assertEqual(DailyClear.lastDue(now, MIDNIGHT, THREE_AM), MIDNIGHT + (3 * HOUR));
    return true;
}

(:test)
function dueIsYesterdayBeforeTheTime(logger as Logger) as Boolean {
    var now = MIDNIGHT + (2 * HOUR);
    Test.assertEqual(
        DailyClear.lastDue(now, MIDNIGHT, THREE_AM), MIDNIGHT + (3 * HOUR) - DailyClear.SECONDS_PER_DAY
    );
    return true;
}

(:test)
function dueAtTheExactMinuteCountsAsPassed(logger as Logger) as Boolean {
    var now = MIDNIGHT + (3 * HOUR);
    Test.assertEqual(DailyClear.lastDue(now, MIDNIGHT, THREE_AM), now);
    return true;
}

(:test)
function dueHandlesMidnightItself(logger as Logger) as Boolean {
    Test.assertEqual(DailyClear.lastDue(MIDNIGHT, MIDNIGHT, 0), MIDNIGHT);
    Test.assertEqual(
        DailyClear.lastDue(MIDNIGHT + 59, MIDNIGHT, DailyClear.MINUTES_PER_DAY - 1),
        MIDNIGHT - 60
    );
    return true;
}

(:test)
function defaultsAreOnAtThreeAm(logger as Logger) as Boolean {
    Application.Storage.clearValues();
    Test.assert(DailyClear.enabled());
    Test.assertEqual(DailyClear.minutes(), 180);
    Test.assertEqualMessage(DailyClear.label(), "03:00", "label");
    return true;
}

(:test)
function aStoredTimeIsReadBackAndFormatted(logger as Logger) as Boolean {
    Application.Storage.clearValues();
    DailyClear.setMinutes((7 * 60) + 5);
    Test.assertEqual(DailyClear.minutes(), 425);
    Test.assertEqualMessage(DailyClear.label(), "07:05", "label");
    return true;
}

(:test)
function anOutOfRangeStoredTimeFallsBackToTheDefault(logger as Logger) as Boolean {
    Application.Storage.setValue(Store.KEY_CLEAR_AT, 99999);
    Test.assertEqual(DailyClear.minutes(), DailyClear.DEFAULT_MINUTES);
    Application.Storage.setValue(Store.KEY_CLEAR_AT, "oops");
    Test.assertEqual(DailyClear.minutes(), DailyClear.DEFAULT_MINUTES);
    return true;
}

(:test)
function firstRunClearsNothingButStartsTheSchedule(logger as Logger) as Boolean {
    seed();
    Test.assert(!DailyClear.apply());
    Test.assertEqual(tickedCount(), 3);
    Test.assert(Application.Storage.getValue(Store.KEY_CLEARED_AT) instanceof Number);
    return true;
}

(:test)
function aMissedClearUnticksEverything(logger as Logger) as Boolean {
    seed();
    // Last cleared at the epoch, so whatever time is set, it has passed since.
    Application.Storage.setValue(Store.KEY_CLEARED_AT, 0);
    Test.assert(DailyClear.apply());
    Test.assertEqual(tickedCount(), 0);
    // Item counts are untouched: only the ticks go.
    Test.assertEqual(Store.checklists().size(), 2);
    return true;
}

(:test)
function itClearsOnlyOncePerDay(logger as Logger) as Boolean {
    seed();
    Application.Storage.setValue(Store.KEY_CLEARED_AT, 0);
    Test.assert(DailyClear.apply());
    Store.setTicked(0, 0, true);
    Test.assert(!DailyClear.apply());
    Test.assertEqual(tickedCount(), 1);
    return true;
}

(:test)
function itDoesNothingWhileSwitchedOff(logger as Logger) as Boolean {
    seed();
    DailyClear.setEnabled(false);
    Application.Storage.setValue(Store.KEY_CLEARED_AT, 0);
    Test.assert(!DailyClear.apply());
    Test.assertEqual(tickedCount(), 3);
    return true;
}

(:test)
function switchingItOnOrMovingTheTimeDoesNotClearAtOnce(logger as Logger) as Boolean {
    seed();
    Application.Storage.setValue(Store.KEY_CLEARED_AT, 0);
    DailyClear.setEnabled(true);
    Test.assert(!DailyClear.apply());
    Application.Storage.setValue(Store.KEY_CLEARED_AT, 0);
    DailyClear.setMinutes(0);
    Test.assert(!DailyClear.apply());
    Test.assertEqual(tickedCount(), 3);
    return true;
}

(:test)
function aSyncCountsAsAClear(logger as Logger) as Boolean {
    seed();
    Application.Storage.setValue(Store.KEY_CLEARED_AT, 0);
    Store.replaceAll([{ "id" => "t:1", "n" => "Test", "i" => ["a"] }] as Array<Dictionary>);
    Test.assert(!DailyClear.apply());
    return true;
}
