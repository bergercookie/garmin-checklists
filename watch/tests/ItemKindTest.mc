import Toybox.Application;
import Toybox.Lang;
import Toybox.Test;

//! Unit tests for the "k" array that says how a list's items are nested.
//! Run with `just watch-test`.

//! A list the bridge unrolled: item 1 is a heading, items 2 and 3 are its
//! linked list's, one level in.
function nested() as Dictionary {
    return {
        "id" => "t:1", "n" => "Evening",
        "i" => ["Lights", "Night routine", "Brush teeth", "Lock door", "Sleep"],
        "d" => [false, false, true, false, false],
        "k" => [0, 1, 2, 2, 0]
    };
}

function plain() as Dictionary {
    return { "id" => "t:2", "n" => "Kit", "i" => ["a", "b"], "d" => [true, false] };
}

(:test)
function aPlainListIsAllDepthZeroAndNoHeadings(logger as Logger) as Boolean {
    var list = plain();
    Test.assertEqual(ItemKind.depth(list, 0), 0);
    Test.assert(!ItemKind.isHeading(list, 1));
    Test.assertEqual(ItemKind.tickable(list), 2);
    Test.assertEqual(ItemKind.ticked(list), 1);
    Test.assertEqual(ItemKind.firstUnticked(list), 1);
    return true;
}

(:test)
function depthIsHalfTheNumberAndOddMeansHeading(logger as Logger) as Boolean {
    var list = nested();
    Test.assertEqual(ItemKind.depth(list, 1), 0);
    Test.assertEqual(ItemKind.depth(list, 2), 1);
    Test.assertEqual(ItemKind.depth(list, 3), 1);
    Test.assert(ItemKind.isHeading(list, 1));
    Test.assert(!ItemKind.isHeading(list, 2));
    return true;
}

(:test)
function headingsAreNotCountedAsThingsToTick(logger as Logger) as Boolean {
    var list = nested();
    Test.assertEqual(ItemKind.tickable(list), 4);
    Test.assertEqual(ItemKind.ticked(list), 1);
    return true;
}

(:test)
function theFirstItemToTickSkipsAHeading(logger as Logger) as Boolean {
    var list = nested();
    var done = list["d"] as Array<Boolean>;
    // Lights is unticked and first.
    Test.assertEqual(ItemKind.firstUnticked(list), 0);
    done[0] = true;
    // Next is the heading at 1, which is skipped, then 2 is ticked, so 3.
    Test.assertEqual(ItemKind.firstUnticked(list), 3);
    done[3] = true;
    done[4] = true;
    Test.assertEqual(ItemKind.firstUnticked(list), -1);
    return true;
}

(:test)
function aMalformedEntryCountsAsAPlainItem(logger as Logger) as Boolean {
    var list = { "i" => ["a", "b", "c"], "d" => [false, false, false], "k" => ["x", -4, null] };
    Test.assertEqual(ItemKind.depth(list, 0), 0);
    Test.assertEqual(ItemKind.depth(list, 1), 0);
    Test.assert(!ItemKind.isHeading(list, 2));
    Test.assert(!ItemKind.isHeading(list, 99));
    return true;
}

(:test)
function aSyncKeepsAWellFormedKAndDropsOneThatDoesNotFit(logger as Logger) as Boolean {
    Application.Storage.clearValues();
    Store.replaceAll(
        [
            { "id" => "t:1", "n" => "Good", "i" => ["a", "b"], "k" => [0, 1] },
            { "id" => "t:2", "n" => "Short", "i" => ["a", "b"], "k" => [0] },
            { "id" => "t:3", "n" => "None", "i" => ["a"] }
        ] as Array<Dictionary>
    );
    var all = Store.checklists();
    Test.assertEqual(all.size(), 3);
    Test.assertEqual((all[0] as Dictionary).hasKey("k"), true);
    Test.assertEqual((all[1] as Dictionary).hasKey("k"), false);
    Test.assertEqual((all[2] as Dictionary).hasKey("k"), false);
    // Ticks start clear for every item, headings included.
    Test.assertEqual(ItemKind.ticked(all[0] as Dictionary), 0);
    return true;
}

(:test)
function clearingTheTicksLeavesTheNestingAlone(logger as Logger) as Boolean {
    Application.Storage.clearValues();
    Store.replaceAll([nested()] as Array<Dictionary>);
    Store.setTicked(0, 2, true);
    Test.assertEqual(ItemKind.ticked(Store.checklists()[0] as Dictionary), 1);
    Store.clearAllTicks();
    var list = Store.checklists()[0] as Dictionary;
    Test.assertEqual(ItemKind.ticked(list), 0);
    Test.assert(ItemKind.isHeading(list, 1));
    Test.assertEqual(ItemKind.depth(list, 2), 1);
    return true;
}
