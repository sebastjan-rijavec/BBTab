"""BBTab application (Adw.Application entry point)."""

from __future__ import annotations

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")

from gi.repository import Adw, Gio  # noqa: E402

from .window import BBTabWindow  # noqa: E402

APP_ID = "com.mildroid.BBTab"


class BBTabApp(Adw.Application):
    def __init__(self):
        super().__init__(application_id=APP_ID,
                         flags=Gio.ApplicationFlags.HANDLES_OPEN)
        self._pending_path = None

    def do_activate(self):
        win = self.props.active_window or BBTabWindow(self)
        if self._pending_path:
            try:
                from .model import Song
                win.song = Song.load(self._pending_path)
                win.path = self._pending_path
                win.fretboard.tuning = win.song.tuning
                win.tabview.set_song(win.song)
                win._sync_title()
                win._update_status()
            except Exception:  # noqa: BLE001
                pass
        win.present()

    def do_open(self, files, _n_files, _hint):
        if files:
            self._pending_path = files[0].get_path()
        self.activate()


def main() -> int:
    return BBTabApp().run(None)
