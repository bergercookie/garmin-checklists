import Toybox.Lang;

//! What a stored checklist's optional "k" array says about its items: how deep
//! each one sits, and which are headings. A heading is the item that stands for
//! a checklist linked from this one; the linked list's items follow it,
//! one level deeper. Headings are shown but never ticked.
//!
//! A list with no "k" -- every list from before links existed, and any list
//! without links -- is all depth 0 and no headings, so nothing here changes
//! how it looks. Everything is read defensively, since the array came off the
//! wire: a missing or malformed entry counts as a plain depth-0 item.
module ItemKind {

    //! How many levels in an item sits; 0 is the list's own items.
    function depth(checklist as Dictionary, index as Number) as Number {
        var value = raw(checklist, index);
        return value / 2;
    }

    //! Whether the item is a heading rather than something to tick.
    function isHeading(checklist as Dictionary, index as Number) as Boolean {
        return raw(checklist, index) % 2 == 1;
    }

    //! The number of items that can be ticked: everything but the headings.
    function tickable(checklist as Dictionary) as Number {
        var items = checklist["i"] as Array<String>;
        var count = 0;
        for (var index = 0; index < items.size(); index += 1) {
            if (!isHeading(checklist, index)) {
                count += 1;
            }
        }
        return count;
    }

    //! How many of those are ticked.
    function ticked(checklist as Dictionary) as Number {
        var done = checklist["d"] as Array<Boolean>;
        var count = 0;
        for (var index = 0; index < done.size(); index += 1) {
            if (done[index] && !isHeading(checklist, index)) {
                count += 1;
            }
        }
        return count;
    }

    //! The first item still to tick, or -1 if there is none.
    function firstUnticked(checklist as Dictionary) as Number {
        var done = checklist["d"] as Array<Boolean>;
        for (var index = 0; index < done.size(); index += 1) {
            if (!done[index] && !isHeading(checklist, index)) {
                return index;
            }
        }
        return -1;
    }

    function raw(checklist as Dictionary, index as Number) as Number {
        var kinds = checklist["k"];
        if (!(kinds instanceof Array) || index < 0 || index >= kinds.size()) {
            return 0;
        }
        var value = kinds[index];
        return value instanceof Number && value > 0 ? value : 0;
    }
}
