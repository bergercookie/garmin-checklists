import Toybox.Lang;
import Toybox.WatchUi;

//! The watch's own settings, reached from the last row of the checklist index.
//!
//! Only preferences that belong to this watch live here. The bridge URL and
//! token are typed in Garmin Connect instead (see AppConfig), and nothing here
//! is ever sent to the bridge.
module SettingsMenu {

    //! Identifier of the "Show clock" toggle.
    const SHOW_CLOCK = :showClock;
    //! Identifier of the "Sync hourly" toggle.
    const AUTO_SYNC = :autoSync;

    function build() as WatchUi.Menu2 {
        var menu = new WatchUi.Menu2({ :title => Clock.title(title()) });
        menu.addItem(
            new WatchUi.ToggleMenuItem(
                WatchUi.loadResource(Rez.Strings.ShowClock) as String,
                WatchUi.loadResource(Rez.Strings.ShowClockHint) as String,
                SHOW_CLOCK,
                Store.showClock(),
                null
            )
        );
        menu.addItem(
            new WatchUi.ToggleMenuItem(
                WatchUi.loadResource(Rez.Strings.SettingAutoSync) as String,
                WatchUi.loadResource(Rez.Strings.SettingAutoSyncHint) as String,
                AUTO_SYNC,
                Store.autoSync(),
                null
            )
        );
        return menu;
    }

    function title() as String {
        return WatchUi.loadResource(Rez.Strings.Settings) as String;
    }
}

class SettingsMenuDelegate extends WatchUi.Menu2InputDelegate {

    private var _menu as WatchUi.Menu2;

    function initialize(menu as WatchUi.Menu2) {
        Menu2InputDelegate.initialize();
        _menu = menu;
    }

    //! The framework has already flipped the toggle; persist it and react.
    function onSelect(item as WatchUi.MenuItem) as Void {
        if (!(item instanceof WatchUi.ToggleMenuItem)) {
            return;
        }
        var id = item.getId();
        if (id == SettingsMenu.SHOW_CLOCK) {
            // Start or stop the minute timer, and redraw this menu's own
            // title to match at once.
            Store.setShowClock(item.isEnabled());
            getApp().clockChanged();
            _menu.setTitle(Clock.title(SettingsMenu.title()));
            WatchUi.requestUpdate();
        } else if (id == SettingsMenu.AUTO_SYNC) {
            // Register or remove the background temporal event to match --
            // this is the only place autoSync can change, so there is no
            // separate "settings changed elsewhere" path to also call this.
            Store.setAutoSync(item.isEnabled());
            AutoSync.schedule();
        }
    }
}
