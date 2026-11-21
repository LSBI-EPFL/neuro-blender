"""
The colour window: select a colour and its transparency in one window.

  - the colour field:      the colour (left to right) and its strength (top = strong, bottom = pale);
  - the brightness bar:    top = bright, bottom = dark;
  - the transparency bar:  0 % = solid, 90 % = almost clear;
  - the preview:           the colour on a checked background, so that you see the transparency;
  - the hex code:          type a hex code and push Enter to use it.

Both front ends use it: the terminal opens it when the user types p, the window opens it with a button.
"""
import colorsys
import tkinter as tk

from matplotlib.colors import to_rgb

from frontends.desktop import sharp_on_windows
from frontends.theme import GROSEILLE, PERLE, RED, TAUPE, mix

FIELD = 240                                                # size of the colour field (pixels on a normal screen)
CHECK = 12                                                 # size of one square of the checked background


def to_hex(rgb):
    return "#%02x%02x%02x" % tuple(round(255 * min(max(c, 0.0), 1.0)) for c in rgb)


class ColourWindow:
    """Build the window with: window = ColourWindow("#e3b04b", 40). Show it and wait with: window.run().
    run() returns (hex code, transparency in %), or None when the user closes the window or pushes Cancel.
    master = the main window of the program (the GUI), or None (the terminal: the colour window is alone)."""

    def __init__(self, colour="#808080", transparency=0, master=None):
        self.result = None
        self.h, self.s, self.v = colorsys.rgb_to_hsv(*to_rgb(colour))
        self.bar_for = None                                # the colour of the brightness bar now (redraw on change)
        self.master = master

        if master is None:
            sharp_on_windows()
        root = self.root = tk.Tk() if master is None else tk.Toplevel(master)
        scale = max(1.0, root.winfo_fpixels("1i") / 96)    # sizes in pixels: larger on a screen with scaling
        self.size, self.check = round(FIELD * scale), round(CHECK * scale)
        root.title("Colour and transparency")
        if master is not None:
            root.transient(master)                         # stays on top of the main window
        root.configure(bg="white", padx=14, pady=12)
        root.attributes("-topmost", True)
        root.resizable(False, False)

        # The colour field: hue from left to right, saturation from top (strong) to bottom (pale).
        self.field = tk.Canvas(root, width=self.size, height=self.size, highlightthickness=0, cursor="crosshair")
        self.field_image = tk.PhotoImage(width=self.size, height=self.size)
        rows = []
        for y in range(self.size):
            saturation = 1 - y / (self.size - 1)
            rows.append("{" + " ".join(to_hex(colorsys.hsv_to_rgb(x / (self.size - 1), saturation, 1.0))
                                       for x in range(self.size)) + "}")
        self.field_image.put(" ".join(rows))
        self.field.create_image(0, 0, image=self.field_image, anchor="nw")
        self.field_marks = [self.field.create_oval(0, 0, 0, 0, outline=c, width=w) for c, w in (("white", 3), ("black", 1))]
        self.field.bind("<Button-1>", self.pick_in_field)
        self.field.bind("<B1-Motion>", self.pick_in_field)

        # The brightness bar.
        self.bar_width = round(26 * scale)
        self.bar = tk.Canvas(root, width=self.bar_width, height=self.size, highlightthickness=0, cursor="sb_v_double_arrow")
        self.bar_image = tk.PhotoImage(width=self.bar_width, height=self.size)
        self.bar.create_image(0, 0, image=self.bar_image, anchor="nw")
        self.bar_mark = self.bar.create_rectangle(0, 0, 0, 0, outline="black", width=2)
        self.bar.bind("<Button-1>", self.pick_in_bar)
        self.bar.bind("<B1-Motion>", self.pick_in_bar)

        # The right column: the preview, the hex code and the transparency.
        side = tk.Frame(root, bg="white", padx=14)
        tk.Label(side, text="Preview", bg="white", fg=TAUPE).pack(anchor="w")
        self.preview = tk.Canvas(side, width=10 * self.check, height=6 * self.check, highlightthickness=1,
                                 highlightbackground=PERLE)
        self.preview.pack(anchor="w", pady=(2, 12))
        tk.Label(side, text="Hex code (type, then Enter)", bg="white", fg=TAUPE).pack(anchor="w")
        self.hex_text = tk.StringVar()
        entry = tk.Entry(side, textvariable=self.hex_text, width=10, relief="solid", bd=1)
        entry.pack(anchor="w", pady=(2, 12))
        entry.bind("<Return>", self.typed_hex)
        self.transparency = tk.IntVar(value=max(0, min(90, int(transparency))))
        tk.Scale(side, from_=0, to=90, resolution=5, orient="horizontal", variable=self.transparency,
                 label="Transparency (%)", length=10 * self.check + 20, bg="white", fg=TAUPE, troughcolor=PERLE,
                 activebackground=RED, highlightthickness=0, bd=0, command=lambda _: self.show()).pack(anchor="w")

        buttons = tk.Frame(root, bg="white", pady=12)
        tk.Button(buttons, text="OK", width=10, bg=RED, fg="white", activebackground=GROSEILLE,
                  activeforeground="white", relief="flat", command=self.ok).pack(side="right")
        tk.Button(buttons, text="Cancel", width=10, bg="white", fg=TAUPE, relief="flat",
                  command=root.destroy).pack(side="right", padx=8)

        self.field.grid(row=0, column=0)
        self.bar.grid(row=0, column=1, padx=(8, 0))
        side.grid(row=0, column=2, sticky="n")
        buttons.grid(row=1, column=0, columnspan=3, sticky="e")
        root.bind("<Escape>", lambda event: root.destroy())
        self.show()

    # ── the actions of the user ──

    def pick_in_field(self, event):
        self.h = min(max(event.x / (self.size - 1), 0.0), 1.0)
        self.s = 1 - min(max(event.y / (self.size - 1), 0.0), 1.0)
        if self.v < 0.05:                                  # black has no colour: make it bright, so the pick shows
            self.v = 1.0
        self.show()

    def pick_in_bar(self, event):
        self.v = 1 - min(max(event.y / (self.size - 1), 0.0), 1.0)
        self.show()

    def typed_hex(self, event=None):
        text = self.hex_text.get().strip()
        text = text if text.startswith("#") else "#" + text
        try:
            self.h, self.s, self.v = colorsys.rgb_to_hsv(*to_rgb(text))
        except ValueError:
            pass                                           # not a hex code: show the last good colour again
        self.show()
        return "break"                                     # Enter in the hex field does not close the window

    def ok(self):
        self.result = (self.colour(), int(self.transparency.get()))
        self.root.destroy()

    # ── drawing ──

    def colour(self):
        return to_hex(colorsys.hsv_to_rgb(self.h, self.s, self.v))

    def show(self):
        """Draw the marks, the brightness bar, the preview and the hex code for the colour now."""
        x, y = self.h * (self.size - 1), (1 - self.s) * (self.size - 1)
        for mark, r in zip(self.field_marks, (7, 5)):
            self.field.coords(mark, x - r, y - r, x + r, y + r)
        if self.bar_for != (self.h, self.s):
            for row in range(self.size):
                self.bar_image.put(to_hex(colorsys.hsv_to_rgb(self.h, self.s, 1 - row / (self.size - 1))),
                                   to=(0, row, self.bar_width, row + 1))
            self.bar_for = (self.h, self.s)
        y = (1 - self.v) * (self.size - 1)
        self.bar.coords(self.bar_mark, 1, y - 2, self.bar_width - 1, y + 2)

        # Tkinter has no transparent colours: mix the colour with each square of the checked background.
        solid, colour = 1 - self.transparency.get() / 100, self.colour()
        self.preview.delete("all")
        for i in range(10):
            for j in range(6):
                square = mix(colour, "#ffffff" if (i + j) % 2 == 0 else PERLE, solid)
                self.preview.create_rectangle(i * self.check, j * self.check, (i + 1) * self.check, (j + 1) * self.check,
                                              fill=square, width=0)
        if self.root.focus_get() is None or not isinstance(self.root.focus_get(), tk.Entry):
            self.hex_text.set(self.colour())

    def run(self):
        self.root.lift()
        self.root.focus_force()
        if self.master is None:
            self.root.mainloop()
        else:                                              # in the GUI: wait until this window closes
            self.root.grab_set()
            self.master.wait_window(self.root)
        return self.result
