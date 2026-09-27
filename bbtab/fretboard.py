"""Interactive fretboard: click a fret to drop a note onto the tab.

Rows are ordered high-e (top) -> low-E (bottom) so a click maps to the same
row in the staff below it. Column 0 is the open string / nut.
"""

from __future__ import annotations

from gi.repository import Gtk, Gdk

from .model import NUM_STRINGS
from .theme import palette

NUM_FRETS = 15  # frets 1..15, plus the open (0) column

PAD_L = 34      # left gutter for string-name labels
PAD_T = 34      # top gutter for fret-number labels
OPEN_W = 40     # width of the open-string (fret 0) column
FRET_W = 46     # width of each fretted column
STRING_GAP = 28

# Frets that get an inlay dot (single), and the one that gets a double dot.
SINGLE_MARKERS = {3, 5, 7, 9, 15}
DOUBLE_MARKER = 12


class FretboardView(Gtk.DrawingArea):
    def __init__(self, tuning):
        super().__init__()
        self.tuning = tuning
        # Callback set by the window: on_fret_clicked(string_index, fret).
        self.on_fret_clicked = None
        self._hover = None  # (string, fret) or None

        width = PAD_L + OPEN_W + NUM_FRETS * FRET_W + 10
        height = PAD_T + STRING_GAP * (NUM_STRINGS - 1) + PAD_T
        self.set_content_width(width)
        self.set_content_height(height)
        self.set_draw_func(self._draw)

        click = Gtk.GestureClick()
        click.connect("pressed", self._on_pressed)
        self.add_controller(click)

        motion = Gtk.EventControllerMotion()
        motion.connect("motion", self._on_motion)
        motion.connect("leave", self._on_leave)
        self.add_controller(motion)

    # ---- geometry --------------------------------------------------------

    def _string_y(self, s: int) -> float:
        return PAD_T + s * STRING_GAP

    def _column_x(self, fret: int) -> float:
        """Left edge of a column. fret 0 == open column."""
        if fret == 0:
            return PAD_L
        return PAD_L + OPEN_W + (fret - 1) * FRET_W

    def _column_center(self, fret: int) -> float:
        if fret == 0:
            return PAD_L + OPEN_W / 2
        return self._column_x(fret) + FRET_W / 2

    def _hit_test(self, x: float, y: float):
        """Map a pixel to (string, fret), or None if outside the grid."""
        top = self._string_y(0) - STRING_GAP / 2
        bottom = self._string_y(NUM_STRINGS - 1) + STRING_GAP / 2
        if y < top or y > bottom:
            return None
        s = round((y - PAD_T) / STRING_GAP)
        if s < 0 or s >= NUM_STRINGS:
            return None
        if x < PAD_L:
            return None
        if x < PAD_L + OPEN_W:
            return (s, 0)
        fret = int((x - PAD_L - OPEN_W) // FRET_W) + 1
        if fret < 1 or fret > NUM_FRETS:
            return None
        return (s, fret)

    # ---- events ----------------------------------------------------------

    def _on_pressed(self, _gesture, _n_press, x, y):
        hit = self._hit_test(x, y)
        if hit and self.on_fret_clicked:
            self.on_fret_clicked(hit[0], hit[1])

    def _on_motion(self, _ctrl, x, y):
        hit = self._hit_test(x, y)
        if hit != self._hover:
            self._hover = hit
            self.queue_draw()

    def _on_leave(self, _ctrl):
        if self._hover is not None:
            self._hover = None
            self.queue_draw()

    # ---- drawing ---------------------------------------------------------

    def _draw(self, _area, cr, width, height, _data=None):
        p = palette()
        cr.set_source_rgb(*p["bg"])
        cr.paint()

        right = self._column_x(NUM_FRETS) + FRET_W
        cr.select_font_face("Sans", 0, 0)

        # Inlay dots (drawn under the wires).
        cr.set_source_rgb(*p["dot"])
        mid_top = self._string_y(0)
        mid_bot = self._string_y(NUM_STRINGS - 1)
        mid = (mid_top + mid_bot) / 2
        for fret in range(1, NUM_FRETS + 1):
            cx = self._column_center(fret)
            if fret == DOUBLE_MARKER:
                q = (mid_bot - mid_top) / 4
                for cy in (mid - q, mid + q):
                    cr.arc(cx, cy, 5, 0, 6.2832)
                    cr.fill()
            elif fret in SINGLE_MARKERS:
                cr.arc(cx, mid, 5, 0, 6.2832)
                cr.fill()

        # Hover highlight.
        if self._hover is not None:
            hs, hf = self._hover
            cx = self._column_center(hf)
            cy = self._string_y(hs)
            cr.set_source_rgba(*p["hover"])
            w = OPEN_W if hf == 0 else FRET_W
            cr.rectangle(cx - w / 2 + 2, cy - STRING_GAP / 2 + 2, w - 4, STRING_GAP - 4)
            cr.fill()

        # Fret wires (vertical). The nut (after the open column) is thicker.
        cr.set_source_rgb(*p["line"])
        for fret in range(0, NUM_FRETS + 1):
            x = self._column_x(fret + 1) if fret < NUM_FRETS else right
            if fret == 0:
                x = PAD_L + OPEN_W  # the nut
                cr.set_line_width(4)
            else:
                cr.set_line_width(1.5)
            cr.move_to(x, self._string_y(0))
            cr.line_to(x, self._string_y(NUM_STRINGS - 1))
            cr.stroke()
        cr.set_line_width(1.5)

        # Strings (horizontal). Thicker toward the low E.
        for s in range(NUM_STRINGS):
            y = self._string_y(s)
            cr.set_line_width(0.8 + s * 0.35)
            cr.move_to(PAD_L, y)
            cr.line_to(right, y)
            cr.stroke()

        # String-name labels on the left.
        cr.set_source_rgb(*p["fg"])
        cr.set_font_size(13)
        for s in range(NUM_STRINGS):
            name = self.tuning[s] if s < len(self.tuning) else "?"
            ext = cr.text_extents(name)
            cr.move_to(PAD_L - 12 - ext.width, self._string_y(s) + ext.height / 2)
            cr.show_text(name)

        # Fret-number labels along the top.
        cr.set_source_rgb(*p["muted"])
        cr.set_font_size(11)
        for fret in range(0, NUM_FRETS + 1):
            label = "0" if fret == 0 else str(fret)
            cx = self._column_center(fret)
            ext = cr.text_extents(label)
            cr.move_to(cx - ext.width / 2, PAD_T - 14)
            cr.show_text(label)
