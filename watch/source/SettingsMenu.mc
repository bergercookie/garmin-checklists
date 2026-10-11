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
    //! Identifier of the "Clear daily" toggle.
    const CLEAR_DAILY = :clearDaily;
    //! Identifier of the "Clear at" row, which opens the time picker.
    const CLEAR_AT = :clearAt;
    //! Identifier of the "Sync hourly" toggle.
    const AUTO_SYNC = :autoSync;

    function push(main as MainDelegate) as Void {
        var view = new ListMenuView(title(), rows(), 0);
        WatchUi.pushView(view, new SettingsMenuDelegate(view, main), WatchUi.SLIDE_LEFT);
    }

    function title() as String {
        return WatchUi.loadResource(Rez.Strings.Settings) as String;
    }

    function rows() as Array<MenuRow> {
        return [
            new MenuRow(
                SHOW_CLOCK, WatchUi.loadResource(Rez.Strings.ShowClock) as String,
                WatchUi.loadResource(Rez.Strings.ShowClockHint) as String, Store.showClock()
            ),
            new MenuRow(
                CLEAR_DAILY, WatchUi.loadResource(Rez.Strings.SettingClearDaily) as String,
                WatchUi.loadResource(Rez.Strings.SettingClearDailyHint) as String,
                DailyClear.enabled()
            ),
            new MenuRow(
                CLEAR_AT, WatchUi.loadResource(Rez.Strings.SettingClearAt) as String,
                DailyClear.label(), null
            ),
            new MenuRow(
                AUTO_SYNC, WatchUi.loadResource(Rez.Strings.SettingAutoSync) as String,
                WatchUi.loadResource(Rez.Strings.SettingAutoSyncHint) as String, Store.autoSync()
            )
        ] as Array<MenuRow>;
    }
}

class SettingsMenuDelegate extends ListMenuDelegate {

    private var _main as MainDelegate;

    function initialize(view as ListMenuView, main as MainDelegate) {
        // Home, the index, then settings.
        ListMenuDelegate.initialize(view, main, 2);
        _main = main;
    }

    function choose(index as Number) as Void {
        var row = _view.row(index);
        if (row == null) {
            return;
        }
        var id = row.id;
        if (id == SettingsMenu.CLEAR_AT) {
            var editor = new ClearTimeView(DailyClear.minutes());
            WatchUi.pushView(
                editor, new ClearTimeDelegate(editor, _main, method(:onClearTimePicked)),
                WatchUi.SLIDE_LEFT
            );
            return;
        }
        var on = row.on;
        if (on == null) {
            return;
        }
        row.on = !on;
        if (id == SettingsMenu.SHOW_CLOCK) {
            // Start or stop the minute timer; the title follows on redraw.
            Store.setShowClock(!on);
            getApp().clockChanged();
        } else if (id == SettingsMenu.CLEAR_DAILY) {
            DailyClear.setEnabled(!on);
        } else if (id == SettingsMenu.AUTO_SYNC) {
            // Register or remove the background temporal event to match --
            // this is the only place autoSync can change, so there is no
            // separate "settings changed elsewhere" path to also call this.
            Store.setAutoSync(!on);
            AutoSync.schedule();
        }
        WatchUi.requestUpdate();
    }

    //! The picker stored a new time; show it.
    function onClearTimePicked() as Void {
        _view.setRows(SettingsMenu.rows());
    }
}
