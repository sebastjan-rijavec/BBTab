"""Main window: fretboard on top, tab staff below, header bar around them."""

from __future__ import annotations

from gi.repository import Adw, Gtk, Gdk, Gio, GLib

from .model import Song, BEND_AMOUNTS
from .fretboard import FretboardView
from .tabview import TabStaffView

FILTER_SUFFIX = ".bbtab"

# Labels shown in the Bend dropdown, aligned with model.BEND_AMOUNTS.
BEND_LABELS = ["no bend", "¼", "½", "full", "1½", "2"]


class BBTabWindow(Adw.ApplicationWindow):
    def __init__(self, app):
        super().__init__(application=app, title="BBTab")
        self.set_default_size(980, 560)

        self.song = Song()
        self.path = None          # current file path or None
        self.dirty = False

        # ---- layout ------------------------------------------------------
        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.set_content(root)

        header = Adw.HeaderBar()
        root.append(header)

        self.title_widget = Adw.WindowTitle(title="Untitled", subtitle="BBTab")
        header.set_title_widget(self.title_widget)

        new_btn = Gtk.Button(icon_name="document-new-symbolic")
        new_btn.set_tooltip_text("New (Ctrl+N)")
        new_btn.connect("clicked", lambda *_: self.action_new())
        header.pack_start(new_btn)

        open_btn = Gtk.Button(icon_name="document-open-symbolic")
        open_btn.set_tooltip_text("Open (Ctrl+O)")
        open_btn.connect("clicked", lambda *_: self.action_open())
        header.pack_start(open_btn)

        save_btn = Gtk.Button(icon_name="document-save-symbolic")
        save_btn.set_tooltip_text("Save (Ctrl+S)")
        save_btn.connect("clicked", lambda *_: self.action_save())
        header.pack_start(save_btn)

        # (The heavily-used navigation controls live in a bottom action bar,
        #  built after the staff below.)

        # Auto-advance toggle: when on, placing a note jumps to the next beat.
        self.auto_toggle = Gtk.ToggleButton(label="Auto-advance")
        self.auto_toggle.set_active(True)
        self.auto_toggle.set_tooltip_text(
            "After you place a note, jump to the next beat.\n"
            "Turn off to stack a chord in one beat."
        )
        header.pack_end(self.auto_toggle)

        # Light / dark theme switcher.
        self.style_manager = Adw.StyleManager.get_default()
        theme_btn = Gtk.MenuButton(icon_name="weather-clear-symbolic")
        theme_btn.set_tooltip_text("Theme: light / dark")
        popover = Gtk.Popover()
        tbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        for m in ("top", "bottom", "start", "end"):
            getattr(tbox, f"set_margin_{m}")(6)
        first = None
        self._theme_radios = {}
        for label, scheme in (("Follow system", Adw.ColorScheme.DEFAULT),
                              ("Light", Adw.ColorScheme.FORCE_LIGHT),
                              ("Dark", Adw.ColorScheme.FORCE_DARK)):
            rb = Gtk.CheckButton(label=label)
            if first is None:
                first = rb
            else:
                rb.set_group(first)
            rb.connect("toggled", self._on_theme_selected, scheme)
            tbox.append(rb)
            self._theme_radios[scheme] = rb
        current = self.style_manager.get_color_scheme()
        self._theme_radios.get(current, first).set_active(True)
        popover.set_child(tbox)
        theme_btn.set_popover(popover)
        header.pack_end(theme_btn)

        # Fretboard.
        self.fretboard = FretboardView(self.song.tuning)
        self.fretboard.on_fret_clicked = self.on_fret_clicked
        fb_scroll = Gtk.ScrolledWindow()
        fb_scroll.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.NEVER)
        fb_scroll.set_child(self.fretboard)
        root.append(fb_scroll)

        root.append(Gtk.Separator())

        # Tab staff.
        self.tabview = TabStaffView(self.song)
        self.tab_scroll = Gtk.ScrolledWindow()
        self.tab_scroll.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.NEVER)
        self.tab_scroll.set_vexpand(True)
        self.tab_scroll.set_child(self.tabview)
        root.append(self.tab_scroll)

        # ---- navigation bar: the buttons used most, big and centred -------
        def nav_button(label, icon, icon_end=False):
            btn = Gtk.Button()
            box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
            box.set_halign(Gtk.Align.CENTER)
            img = Gtk.Image.new_from_icon_name(icon)
            lbl = Gtk.Label(label=label)
            if icon_end:
                box.append(lbl)
                box.append(img)
            else:
                box.append(img)
                box.append(lbl)
            btn.set_child(box)
            btn.set_size_request(132, 46)
            return btn

        navbar = Gtk.ActionBar()

        nav_group = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        nav_group.add_css_class("linked")

        self.back_btn = nav_button("Back", "go-previous-symbolic")
        self.back_btn.set_tooltip_text("Previous beat  (←)")
        self.back_btn.connect("clicked", lambda *_: self.step_back())
        nav_group.append(self.back_btn)

        self.next_btn = nav_button("Next", "go-next-symbolic", icon_end=True)
        self.next_btn.set_tooltip_text("Next beat  (Space / →)")
        self.next_btn.connect("clicked", lambda *_: self.advance())
        nav_group.append(self.next_btn)

        navbar.set_center_widget(nav_group)

        self.pos_label = Gtk.Label(xalign=0)
        self.pos_label.add_css_class("dim-label")
        self.pos_label.set_margin_start(6)
        navbar.pack_start(self.pos_label)

        clear_btn = Gtk.Button(icon_name="edit-clear-symbolic")
        clear_btn.set_tooltip_text("Clear the whole beat  (Shift+Delete)")
        clear_btn.connect("clicked", lambda *_: self.clear_beat())
        navbar.pack_end(clear_btn)

        del_note_btn = Gtk.Button(icon_name="list-remove-symbolic")
        del_note_btn.set_tooltip_text("Delete just the selected note  (Delete)")
        del_note_btn.connect("clicked", lambda *_: self.delete_selected_note())
        navbar.pack_end(del_note_btn)

        # ---- techniques bar: everything that acts on the selected note ----
        techbar = Gtk.ActionBar()

        heading = Gtk.Label(label="Selected note")
        heading.add_css_class("dim-label")
        techbar.pack_start(heading)

        # Bend (press 'b' to cycle).
        bend_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        bend_box.append(Gtk.Label(label="Bend"))
        self.bend_drop = Gtk.DropDown.new_from_strings(BEND_LABELS)
        self.bend_drop.set_tooltip_text("Bend amount for the selected note  (press 'b' to cycle)")
        self._suppress_bend = False
        self.bend_drop.connect("notify::selected", self._on_bend_changed)
        bend_box.append(self.bend_drop)
        techbar.pack_start(bend_box)

        # Hold: beats the note sustains / bends across.
        hold_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        hold_box.append(Gtk.Label(label="Hold"))
        self.hold_spin = Gtk.SpinButton.new_with_range(0, 16, 1)
        self.hold_spin.set_tooltip_text(
            "Beats the selected note is held / bent across.\n"
            "Other strings can be played in those beats."
        )
        self._suppress_hold = False
        self.hold_spin.connect("value-changed", self._on_hold_changed)
        hold_box.append(self.hold_spin)
        techbar.pack_start(hold_box)

        # Vibrato ('v'), rendered as a trailing 'v'.
        self.vib_toggle = Gtk.ToggleButton(label="Vibrato")
        self.vib_toggle.set_tooltip_text("Vibrato on the selected note  (press 'v')")
        self._suppress_vib = False
        self.vib_toggle.connect("toggled", self._on_vibrato_toggled)
        techbar.pack_start(self.vib_toggle)

        # Slides: 'to' lands on this note ('/9'); 'from' leaves it ('7/').
        self.slide_in_toggle = Gtk.ToggleButton(label="Slide to")
        self.slide_in_toggle.set_tooltip_text(
            "Slide up/down INTO the selected note  (press '\\')")
        self._suppress_slide = False
        self.slide_in_toggle.connect("toggled", self._on_slide_in_toggled)
        techbar.pack_start(self.slide_in_toggle)

        self.slide_out_toggle = Gtk.ToggleButton(label="Slide from")
        self.slide_out_toggle.set_tooltip_text(
            "Slide FROM the selected note to the next note on its string  (press '/')")
        self.slide_out_toggle.connect("toggled", self._on_slide_out_toggled)
        techbar.pack_start(self.slide_out_toggle)

        root.append(techbar)
        root.append(navbar)

        # Keep the technique controls in sync when the selection changes.
        self.tabview.on_selection_changed = self._sync_bend_ui

        # Hint / status bar.
        self.status = Gtk.Label(xalign=0)
        self.status.add_css_class("dim-label")
        self.status.set_margin_start(10)
        self.status.set_margin_top(4)
        self.status.set_margin_bottom(6)
        root.append(self.status)
        self._update_status()

        # Redraw the custom canvases whenever the light/dark state flips.
        self.style_manager.connect("notify::dark", self._on_dark_changed)

        # ---- keyboard ----------------------------------------------------
        keys = Gtk.EventControllerKey()
        keys.connect("key-pressed", self.on_key)
        self.add_controller(keys)

    def _on_theme_selected(self, btn, scheme):
        if btn.get_active():
            self.style_manager.set_color_scheme(scheme)

    def _on_dark_changed(self, *_args):
        self.fretboard.queue_draw()
        self.tabview.queue_draw()

    # ---- editing ---------------------------------------------------------

    def on_fret_clicked(self, string_index: int, fret: int):
        self.song.beats[self.tabview.cursor].set_note(string_index, fret)
        self.tabview.sel_string = string_index  # select what you just placed
        self._mark_dirty()
        self.tabview.refresh()
        self._sync_bend_ui()
        self._update_status()
        if self.auto_toggle.get_active():
            self.advance()

    # ---- bends -----------------------------------------------------------

    def _on_bend_changed(self, drop, _param):
        if self._suppress_bend:
            return
        note = self.tabview.selected_note()
        if note is None:
            self._sync_bend_ui()  # nothing selected: snap back
            return
        note.bend = BEND_AMOUNTS[drop.get_selected()]
        self._mark_dirty()
        self.tabview.queue_draw()
        self._update_status()

    def _on_hold_changed(self, spin):
        if self._suppress_hold:
            return
        note = self.tabview.selected_note()
        if note is None:
            self._sync_bend_ui()  # nothing selected: snap back
            return
        note.hold = int(spin.get_value())
        self._mark_dirty()
        self.tabview.refresh()

    def _on_vibrato_toggled(self, btn):
        if self._suppress_vib:
            return
        note = self.tabview.selected_note()
        if note is None:
            self._sync_bend_ui()  # nothing selected: snap back
            return
        note.vibrato = btn.get_active()
        self._mark_dirty()
        self.tabview.queue_draw()

    def toggle_vibrato(self):
        note = self.tabview.selected_note()
        if note is None:
            return
        note.vibrato = not note.vibrato
        self._mark_dirty()
        self._sync_bend_ui()
        self.tabview.queue_draw()

    def _on_slide_in_toggled(self, btn):
        if self._suppress_slide:
            return
        note = self.tabview.selected_note()
        if note is None:
            self._sync_bend_ui()
            return
        note.slide_in = btn.get_active()
        self._mark_dirty()
        self.tabview.queue_draw()

    def _on_slide_out_toggled(self, btn):
        if self._suppress_slide:
            return
        note = self.tabview.selected_note()
        if note is None:
            self._sync_bend_ui()
            return
        note.slide_out = btn.get_active()
        self._mark_dirty()
        self.tabview.queue_draw()

    def toggle_slide(self, which):
        """which: 'in' or 'out'."""
        note = self.tabview.selected_note()
        if note is None:
            return
        if which == "in":
            note.slide_in = not note.slide_in
        else:
            note.slide_out = not note.slide_out
        self._mark_dirty()
        self._sync_bend_ui()
        self.tabview.queue_draw()

    def _sync_bend_ui(self):
        """Reflect the selected note's bend + hold in the controls, no re-apply."""
        note = self.tabview.selected_note()
        amount = note.bend if note else 0.0
        idx = BEND_AMOUNTS.index(amount) if amount in BEND_AMOUNTS else 0
        self._suppress_bend = True
        self.bend_drop.set_selected(idx)
        self._suppress_bend = False

        self._suppress_hold = True
        self.hold_spin.set_value(note.hold if note else 0)
        self._suppress_hold = False

        self._suppress_vib = True
        self.vib_toggle.set_active(bool(note.vibrato) if note else False)
        self._suppress_vib = False

        self._suppress_slide = True
        self.slide_in_toggle.set_active(bool(note.slide_in) if note else False)
        self.slide_out_toggle.set_active(bool(note.slide_out) if note else False)
        self._suppress_slide = False

    def cycle_bend(self):
        note = self.tabview.selected_note()
        if note is None:
            return
        cur = BEND_AMOUNTS.index(note.bend) if note.bend in BEND_AMOUNTS else 0
        note.bend = BEND_AMOUNTS[(cur + 1) % len(BEND_AMOUNTS)]
        self._mark_dirty()
        self._sync_bend_ui()
        self.tabview.queue_draw()
        self._update_status()

    def advance(self):
        cur = self.tabview.cursor
        if cur >= len(self.song.beats) - 1:
            self.song.append_beat()
            self.tabview.refresh()
        self.tabview.set_cursor(cur + 1)
        self._scroll_to_cursor()
        self._update_status()

    def step_back(self):
        self.tabview.set_cursor(self.tabview.cursor - 1)
        self._scroll_to_cursor()
        self._update_status()

    def clear_beat(self):
        self.song.beats[self.tabview.cursor].notes.clear()
        self._mark_dirty()
        self.tabview.refresh()
        self._sync_bend_ui()
        self._update_status()

    def delete_selected_note(self):
        """Remove only the selected note, leaving any others in the beat."""
        beat = self.song.beats[self.tabview.cursor]
        if self.tabview.sel_string in beat.notes:
            beat.clear_string(self.tabview.sel_string)
            self._mark_dirty()
            self.tabview.refresh()
            self._sync_bend_ui()
            self._update_status()

    def backspace(self):
        """Clear the current beat; if already empty, delete it and step back."""
        beat = self.song.beats[self.tabview.cursor]
        if beat.notes:
            beat.notes.clear()
        elif len(self.song.beats) > 1:
            del self.song.beats[self.tabview.cursor]
            self.tabview.set_cursor(self.tabview.cursor - 1)
        self._mark_dirty()
        self.tabview.refresh()
        self._scroll_to_cursor()
        self._update_status()

    def _scroll_to_cursor(self):
        adj = self.tab_scroll.get_hadjustment()
        from .tabview import PAD_L, COL_W
        x = PAD_L + self.tabview.cursor * COL_W
        page = adj.get_page_size()
        if x < adj.get_value():
            adj.set_value(max(0, x - COL_W))
        elif x + COL_W > adj.get_value() + page:
            adj.set_value(x + COL_W - page)

    # ---- keyboard --------------------------------------------------------

    def on_key(self, _ctrl, keyval, _keycode, state):
        ctrl = bool(state & Gdk.ModifierType.CONTROL_MASK)
        if ctrl:
            if keyval == Gdk.KEY_s:
                self.action_save(); return True
            if keyval == Gdk.KEY_o:
                self.action_open(); return True
            if keyval == Gdk.KEY_n:
                self.action_new(); return True
            return False

        if keyval in (Gdk.KEY_space, Gdk.KEY_Right):
            if keyval == Gdk.KEY_Right:
                self.tabview.set_cursor(self.tabview.cursor + 1)
                self._scroll_to_cursor(); self._update_status()
            else:
                self.advance()
            return True
        if keyval == Gdk.KEY_Left:
            self.step_back(); return True
        if keyval in (Gdk.KEY_Up, Gdk.KEY_Down):
            step = -1 if keyval == Gdk.KEY_Up else 1  # Up = higher string (lower index)
            from .model import NUM_STRINGS
            self.tabview.sel_string = max(0, min(self.tabview.sel_string + step,
                                                 NUM_STRINGS - 1))
            self.tabview.queue_draw(); self._sync_bend_ui(); self._update_status()
            return True
        if keyval in (Gdk.KEY_b, Gdk.KEY_B):
            self.cycle_bend(); return True
        if keyval in (Gdk.KEY_v, Gdk.KEY_V):
            self.toggle_vibrato(); return True
        if keyval == Gdk.KEY_slash:
            self.toggle_slide("out"); return True
        if keyval == Gdk.KEY_backslash:
            self.toggle_slide("in"); return True
        if keyval in (Gdk.KEY_Delete,):
            if state & Gdk.ModifierType.SHIFT_MASK:
                self.clear_beat()        # Shift+Delete: whole beat
            else:
                self.delete_selected_note()  # Delete: just the selected note
            return True
        if keyval in (Gdk.KEY_BackSpace,):
            self.backspace(); return True
        return False

    # ---- file actions ----------------------------------------------------

    def action_new(self):
        self.song = Song()
        self.path = None
        self.dirty = False
        self.fretboard.tuning = self.song.tuning
        self.tabview.set_song(self.song)
        self._sync_title()
        self._update_status()

    def action_open(self):
        dialog = Gtk.FileDialog(title="Open tablature")
        dialog.open(self, None, self._on_open_done)

    def _on_open_done(self, dialog, result):
        try:
            gfile = dialog.open_finish(result)
        except GLib.Error:
            return
        if not gfile:
            return
        path = gfile.get_path()
        try:
            self.song = Song.load(path)
        except Exception as exc:  # noqa: BLE001 - surface any load error
            self._toast_error(f"Could not open: {exc}")
            return
        self.path = path
        self.dirty = False
        self.fretboard.tuning = self.song.tuning
        self.tabview.set_song(self.song)
        self._sync_title()
        self._update_status()

    def action_save(self):
        if self.path:
            self._write(self.path)
        else:
            dialog = Gtk.FileDialog(title="Save tablature")
            dialog.set_initial_name(f"{self.song.title}{FILTER_SUFFIX}")
            dialog.save(self, None, self._on_save_done)

    def _on_save_done(self, dialog, result):
        try:
            gfile = dialog.save_finish(result)
        except GLib.Error:
            return
        if not gfile:
            return
        path = gfile.get_path()
        if not path.endswith(FILTER_SUFFIX):
            path += FILTER_SUFFIX
        self.path = path
        self._write(path)

    def _write(self, path: str):
        try:
            self.song.save(path)
        except Exception as exc:  # noqa: BLE001
            self._toast_error(f"Could not save: {exc}")
            return
        self.dirty = False
        self._sync_title()

    # ---- misc ------------------------------------------------------------

    def _mark_dirty(self):
        if not self.dirty:
            self.dirty = True
            self._sync_title()

    def _sync_title(self):
        import os
        name = os.path.basename(self.path) if self.path else "Untitled"
        self.title_widget.set_title(("• " if self.dirty else "") + name)

    def _update_status(self):
        from .model import bend_label
        beat = self.song.beats[self.tabview.cursor]
        n = len(self.song.beats)
        measure = self.tabview.cursor // max(1, self.song.beats_per_measure) + 1
        notes = ", ".join(
            f"{self.song.tuning[s]}:{note.fret}{bend_label(note.bend)}"
            for s, note in sorted(beat.notes.items())
        ) or "empty"
        sel = self.song.tuning[self.tabview.sel_string]
        self.status.set_text(
            f"{notes}     —  selected string: {sel} · "
            "↑↓ pick string · Delete removes just this note · Shift+Delete clears the beat"
        )
        self.pos_label.set_text(f"Beat {self.tabview.cursor + 1}/{n} · measure {measure}")
        self.back_btn.set_sensitive(self.tabview.cursor > 0)
        self._sync_bend_ui()

    def _toast_error(self, message: str):
        dialog = Adw.AlertDialog(heading="BBTab", body=message)
        dialog.add_response("ok", "OK")
        dialog.present(self)
