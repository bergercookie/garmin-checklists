import Toybox.Application;
import Toybox.Lang;

//! The values the user sets in Garmin Connect, read on demand.
//!
//! Nothing is cached: Properties access is cheap and a cache would only add a
//! way for the app to disagree with the phone after a settings change.
//!
//! Annotated for the background process, which can read properties (but never
//! write them) and needs the bridge URL and the token. Whether auto-sync
//! itself is on lives in Store instead: it is a watch-side toggle, not a
//! Garmin Connect setting -- see Store.autoSync.
(:background)
module AppConfig {

    //! Root URL of the bridge, e.g. "https://checklists.example.com".
    function bridgeUrl() as String {
        return trimmed(read("bridgeUrl"));
    }

    //! Pairing token shown on the bridge's web page.
    function deviceToken() as String {
        return trimmed(read("deviceToken"));
    }

    //! True once both settings have been filled in.
    function isReady() as Boolean {
        return bridgeUrl().length() > 0 && deviceToken().length() > 0;
    }

    //! Absolute URL for a bridge path such as "/api/v1/watch/lists".
    function url(path as String) as String {
        var base = bridgeUrl();
        if (slice(base, base.length() - 1, base.length()).equals("/")) {
            base = slice(base, 0, base.length() - 1);
        }
        return base + path;
    }

    //! Headers every bridge request carries.
    function headers() as Dictionary<String, String> {
        return { "Authorization" => "Bearer " + deviceToken() };
    }

    function read(key as String) as String {
        var value = null;
        try {
            value = Properties.getValue(key);
        } catch (error) {
            value = null;
        }
        return value instanceof String ? value : "";
    }

    //! Monkey C has no String.trim(); users paste URLs with stray spaces.
    function trimmed(text as String) as String {
        var start = 0;
        var end = text.length();
        while (start < end && isSpace(slice(text, start, start + 1))) {
            start += 1;
        }
        while (end > start && isSpace(slice(text, end - 1, end))) {
            end -= 1;
        }
        return slice(text, start, end);
    }

    //! String.substring returns null for an out-of-range slice, which the
    //! strict type checker rightly refuses to let us ignore.
    function slice(text as String, start as Number, end as Number) as String {
        var part = text.substring(start, end);
        if (part == null) {
            return "";
        }
        return part;
    }

    function isSpace(character as String) as Boolean {
        return character.equals(" ") || character.equals("\t") || character.equals("\n");
    }
}
