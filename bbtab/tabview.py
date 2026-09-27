"""The tab staff: renders the Song and a movable cursor, and lets you click a
column to move the cursor there. Sits inside a horizontal ScrolledWindow.
"""

from __future__ import annotations

from gi.repository import Gtk

from .model import NUM_STRINGS, Song, bend_label
from .theme import palette

PAD_L = 34       # left gutter for string labels
PAD_T = 26
STRING_GAP = 22
COL_W = 34       # width of one beat column
TRAILING = 2     # extra empty columns drawn past the last beat


class TabStaffView(Gtk.DrawingArea):
    def __init__(self, song: Song):
        super().__init__()
        self.song = song
        self.cursor = 0       # selected beat (column index into song.beats)
        self.sel_string = 0   # selected string (row) for per-note techniques
        self.on_cursor_moved = None      # optional callback(index)
        self.on_selection_changed = None  # optional callback()

        self.set_content_height(PAD_T * 2 + STRING_GAP * (NUM_STRINGS - 1))
        self.set_draw_func(self._draw)
        self._refresh_width()

        click = Gtk.GestureClick()
        click.connect("pressed", self._on_pressed)
        self.add_controller(click)

    # ---- geometry --------------------------------------------------------

    def _string_y(self, s: int) -> float:
        return PAD_T + s * STRING_GAP

    def _column_center(self, i: int) -> float:
        return PAD_L + i * COL_W + COL_W / 2

    def _refresh_width(self):
        cols = len(self.song.beats) + TRAILING
        self.set_content_width(PAD_L + cols * COL_W + PAD_L)

    def set_song(self, song: Song):
        self.song = song
        self.cursor = 0
        self._refresh_width()
        self.queue_draw()

    def set_cursor(self, index: int):
        index = max(0, min(index, len(self.song.beats) - 1))
        self.cursor = index
        if self.on_cursor_moved:
            self.on_cursor_moved(index)
        self.queue_draw()

    def refresh(self):
        self._refresh_width()
        self.queue_draw()

    def selected_note(self):
        """The Note at (cursor, sel_string), or None."""
        return self.song.beats[self.cursor].notes.get(self.sel_string)

    # ---- events ----------------------------------------------------------

    def _on_pressed(self, _gesture, _n_press, x, y):
        i = int((x - PAD_L) // COL_W)
        if not (0 <= i < len(self.song.beats)):
            return
        self.cursor = i
        s = round((y - PAD_T) / STRING_GAP)
        self.sel_string = max(0, min(s, NUM_STRINGS - 1))
        if self.on_cursor_moved:
            self.on_cursor_moved(i)
        if self.on_selection_changed:
            self.on_selection_changed()
        self.queue_draw()

    # ---- drawing ---------------------------------------------------------

    def _draw(self, _area, cr, width, height, _data=None):
        p = palette()
        cr.set_source_rgb(*p["bg"])
        cr.paint()

        n_cols = len(self.song.beats) + TRAILING
        right = self._column_center(n_cols - 1) + COL_W / 2

        # Cursor column highlight (under the lines).
        cr.set_source_rgba(*p["cursor"])
        cx = self._column_center(self.cursor)
        cr.rectangle(cx - COL_W / 2, PAD_T - 12,
                     COL_W, STRING_GAP * (NUM_STRINGS - 1) + 24)
        cr.fill()

        # Six horizontal string lines.
        cr.set_source_rgb(*p["line"])
        cr.set_line_width(1.0)
        for s in range(NUM_STRINGS):
            y = self._string_y(s)
            cr.move_to(PAD_L, y)
            cr.line_to(right, y)
            cr.stroke()

        # Bar lines every `beats_per_measure`.
        bpm = max(1, self.song.beats_per_measure)
        top_y, bot_y = self._string_y(0), self._string_y(NUM_STRINGS - 1)
        cr.set_source_rgb(*p["muted"])
        for i in range(0, n_cols + 1, bpm):
            bx = PAD_L + i * COL_W
            cr.move_to(bx, top_y)
            cr.line_to(bx, bot_y)
            cr.stroke()

        # "TAB" style string labels on the left.
        cr.select_font_face("Sans", 0, 0)
        cr.set_source_rgb(*p["muted"])
        cr.set_font_size(12)
        for s in range(NUM_STRINGS):
            name = self.song.tuning[s] if s < len(self.song.tuning) else "?"
            ext = cr.text_extents(name)
            cr.move_to(PAD_L - 14 - ext.width, self._string_y(s) + ext.height / 2)
            cr.show_text(name)

        # Fret numbers (+ bend suffix). A bg rect behind each "breaks" the line.
        for i, beat in enumerate(self.song.beats):
            cx = self._column_center(i)
            for s, note in beat.notes.items():
                num = str(note.fret)
                suf = bend_label(note.bend) + ("v" if note.vibrato else "")
                y = self._string_y(s)

                cr.set_font_size(14)
                num_ext = cr.text_extents(num)
                suf_w = 0.0
                if suf:
                    cr.set_font_size(10)
                    suf_w = cr.text_extents(suf).width + 2
                total_w = num_ext.width + suf_w
                left = cx - total_w / 2

                # background break
                cr.set_source_rgb(*p["bg"])
                cr.rectangle(left - 3, y - 10, total_w + 6, 20)
                cr.fill()

                # selection ring
                if i == self.cursor and s == self.sel_string:
                    cr.set_source_rgb(*p["accent"])
                    cr.set_line_width(1.5)
                    cr.rectangle(left - 4, y - 10, total_w + 8, 20)
                    cr.stroke()

                # fret number
                cr.set_source_rgb(*p["fg"])
                cr.set_font_size(14)
                cr.move_to(left, y + num_ext.height / 2)
                cr.show_text(num)

                # bend suffix, smaller + raised, in the accent colour
                if suf:
                    cr.set_source_rgb(*p["accent"])
                    cr.set_font_size(10)
                    cr.move_to(left + num_ext.width + 2, y - 2)
                    cr.show_text(suf)

                # slides: '/' rising or '\' falling. slide_out sits after the
                # number (toward the next note), slide_in before it.
                def slash(x0, rising):
                    cr.set_source_rgb(*p["fg"])
                    cr.set_line_width(1.8)
                    if rising:
                        cr.move_to(x0, y + 5)
                        cr.line_to(x0 + 9, y - 5)
                    else:
                        cr.move_to(x0, y - 5)
                        cr.line_to(x0 + 9, y + 5)
                    cr.stroke()

                if note.slide_out:
                    rising = True  # default direction until a target exists
                    for j in range(i + 1, len(self.song.beats)):
                        tgt = self.song.beats[j].notes.get(s)
                        if tgt is not None:
                            rising = tgt.fret >= note.fret
                            break
                    slash(left + total_w + 2, rising)

                if note.slide_in:
                    rising = True  # default: slide up into the note
                    for j in range(i - 1, -1, -1):
                        src = self.song.beats[j].notes.get(s)
                        if src is not None:
                            rising = note.fret >= src.fret
                            break
                    slash(left - 11, rising)

                # hold / bend-duration line spanning `hold` beats to the right.
                if note.hold > 0:
                    end_i = min(i + note.hold, len(self.song.beats) + TRAILING - 1)
                    x1 = left + total_w + 4
                    x2 = self._column_center(end_i)
                    if x2 > x1:
                        cr.set_source_rgb(*(p["accent"] if note.bend else p["muted"]))
                        cr.set_line_width(1.8)
                        cr.move_to(x1, y)
                        cr.line_to(x2, y)
                        cr.stroke()
                        cr.move_to(x2, y - 4)  # end cap
                        cr.line_to(x2, y + 4)
                        cr.stroke()
