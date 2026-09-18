import Toybox.Communications;
import Toybox.Lang;
import Toybox.WatchUi;

//! Pulls the current checklists from the bridge, one request per list.
//!
//! The index is fetched first so the watch knows what to ask for and can refuse
//! an unreasonable amount of it up front. Everything fetched is held in memory
//! until the last response arrives and is handed over in one go, so the peak is
//! roughly the whole corpus twice over -- which is why MAX_LISTS exists rather
//! than being left to the heap to discover.
//!
//! This is the one fetch path, shared by the interactive sync (MainDelegate)
//! and the background auto-sync (AutoSyncService). The background process has
//! no WatchUi, no string resources and a 64 KB heap, so this class only fetches
//! and reports a numeric status; storing the result and wording a message is
//! done by its caller. Either way it makes the same two read-only GETs and
//! nothing else: nothing is ever sent back to the bridge.
(:background)
class SyncTask {

    //! Upper bound on how many lists one sync will pull. The watch holds them
    //! all in memory before writing, and an unbounded index from a server that
    //! has gone wrong would end the sync in an out-of-memory kill with no
    //! message at all.
    static const MAX_LISTS = 40;

    //! The background process is killed after 30 seconds and has a far smaller
    //! heap, so it refuses an index longer than this rather than dying part way
    //! through every hour. It refuses rather than truncating: a background sync
    //! must never leave the watch with fewer lists than a manual one would.
    //! A guess, to be tuned on a real watch.
    static const BACKGROUND_MAX_LISTS = 15;

    //! Every request came back 200 and the lists are complete.
    static const OK = 200;
    //! Statuses of our own. HTTP codes are positive and Communications error
    //! codes run from 0 down to -1007, so these cannot collide.
    static const NOT_CONFIGURED = -9001;
    static const BAD_RESPONSE = -9002;
    static const TOO_MANY = -9003;

    private var _onDone as Method(status as Number, lists as Array<Dictionary>) as Void;
    private var _background as Boolean;
    private var _pending as Array<String>;
    private var _collected as Array<Dictionary>;

    //! @param onDone called exactly once: with OK and every list, or with
    //!   a failure status and an empty array.
    //! @param background true in the background process; see
    //!   BACKGROUND_MAX_LISTS.
    function initialize(
        onDone as Method(status as Number, lists as Array<Dictionary>) as Void,
        background as Boolean
    ) {
        _onDone = onDone;
        _background = background;
        _pending = [] as Array<String>;
        _collected = [] as Array<Dictionary>;
    }

    //! Kick the sync off. Safe to call only once per instance.
    //!
    //! The options dictionary is written out at both call sites rather than
    //! shared from a helper: makeWebRequest takes a keyed dictionary type, and
    //! a dictionary literal erases to a plain Dictionary when it is returned
    //! from a function, which the strict type checker rejects.
    function start() as Void {
        if (!AppConfig.isReady()) {
            fail(NOT_CONFIGURED);
            return;
        }
        Communications.makeWebRequest(
            AppConfig.url("/api/v1/watch/lists"),
            { "refresh" => "true" },
            {
                :method => Communications.HTTP_REQUEST_METHOD_GET,
                :headers => AppConfig.headers(),
                :responseType => Communications.HTTP_RESPONSE_CONTENT_TYPE_JSON
            },
            method(:onIndex)
        );
    }

    //! Response to the index request: remember which lists to fetch.
    function onIndex(responseCode as Number, data as Dictionary or String or Null) as Void {
        if (responseCode != 200) {
            fail(responseCode);
            return;
        }
        // A 200 whose body is the wrong shape is not a transport failure, so it
        // must not be reported as "Sync failed (200)" -- which reads as a
        // contradiction and tells the user nothing.
        if (!(data instanceof Dictionary)) {
            fail(BAD_RESPONSE);
            return;
        }
        var lists = data["l"];
        if (!(lists instanceof Array)) {
            fail(BAD_RESPONSE);
            return;
        }
        if (_background && lists.size() > BACKGROUND_MAX_LISTS) {
            fail(TOO_MANY);
            return;
        }
        // `as` is a compile-time assertion, not a runtime check, so every field
        // out of a parsed response is tested before it is used. A proxy error
        // page rendered as JSON would otherwise take the app down with the
        // Connect IQ crash screen.
        for (var index = 0; index < lists.size() && _pending.size() < MAX_LISTS; index += 1) {
            var entry = lists[index];
            if (!(entry instanceof Dictionary)) {
                continue;
            }
            var id = entry["id"];
            if (id instanceof String && id.length() > 0) {
                _pending.add(id);
            }
        }
        if (_pending.size() == 0 && lists.size() > 0) {
            fail(BAD_RESPONSE);
            return;
        }
        fetchNext();
    }

    //! Response to one checklist request.
    function onList(responseCode as Number, data as Dictionary or String or Null) as Void {
        if (responseCode != 200) {
            fail(responseCode);
            return;
        }
        if (!(data instanceof Dictionary)) {
            fail(BAD_RESPONSE);
            return;
        }
        _collected.add(data);
        fetchNext();
    }

    private function fetchNext() as Void {
        if (_pending.size() == 0) {
            _onDone.invoke(OK, _collected);
            return;
        }
        var next = _pending[0];
        _pending = _pending.slice(1, null);
        Communications.makeWebRequest(
            AppConfig.url("/api/v1/watch/lists/" + next),
            null,
            {
                :method => Communications.HTTP_REQUEST_METHOD_GET,
                :headers => AppConfig.headers(),
                :responseType => Communications.HTTP_RESPONSE_CONTENT_TYPE_JSON
            },
            method(:onList)
        );
    }

    //! Never called with OK: only fetchNext reports success, with the lists.
    private function fail(status as Number) as Void {
        _onDone.invoke(status, [] as Array<Dictionary>);
    }
}

//! The foreground half of an interactive sync: store the result and word it.
//!
//! Kept out of SyncTask because WatchUi and the string resources do not exist
//! in the background process.
module SyncOutcome {

    //! Apply a finished SyncTask and return the message for the home screen.
    //! Only a complete fetch touches storage, and it replaces all of it, ticks
    //! included.
    function apply(status as Number, lists as Array<Dictionary>) as String {
        if (status == SyncTask.OK) {
            Store.replaceAll(lists);
            return WatchUi.loadResource(Rez.Strings.SyncOk) as String;
        }
        return describe(status);
    }

    //! Turn a status into something that fits on a watch face.
    //!
    //! A bare number is the worst thing to show here: -1001 is the single most
    //! likely setup mistake (an http:// URL) and reads as gibberish, and -403
    //! reads as an HTTP permission error when it means the reply was too big.
    function describe(status as Number) as String {
        if (status == SyncTask.NOT_CONFIGURED) {
            return WatchUi.loadResource(Rez.Strings.NotConfigured) as String;
        }
        if (status == SyncTask.BAD_RESPONSE) {
            return WatchUi.loadResource(Rez.Strings.BadResponse) as String;
        }
        if (status == 401 || status == 403) {
            return WatchUi.loadResource(Rez.Strings.BadToken) as String;
        }
        if (status == Communications.SECURE_CONNECTION_REQUIRED) {
            return WatchUi.loadResource(Rez.Strings.NeedsHttps) as String;
        }
        if (status == Communications.BLE_CONNECTION_UNAVAILABLE
            || status == Communications.BLE_HOST_TIMEOUT) {
            return WatchUi.loadResource(Rez.Strings.NoPhone) as String;
        }
        if (status == Communications.NETWORK_RESPONSE_TOO_LARGE
            || status == Communications.NETWORK_RESPONSE_OUT_OF_MEMORY
            || status == SyncTask.TOO_MANY) {
            return WatchUi.loadResource(Rez.Strings.TooBig) as String;
        }
        if (status == Communications.NETWORK_REQUEST_TIMED_OUT) {
            return WatchUi.loadResource(Rez.Strings.TimedOut) as String;
        }
        return (WatchUi.loadResource(Rez.Strings.SyncFailed) as String) + " (" + status + ")";
    }
}
