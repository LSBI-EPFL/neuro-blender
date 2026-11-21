"""
Draw a window of the tool into an image file WITHOUT a screen capture.

The drawing reads each Tk widget (position, size, colours, text, font, canvas items) and draws it with Pillow.
So the image can never show another window or private content of the screen. It is a layout check, not an exact
copy: the fonts are Segoe UI (Windows), the dropdowns and scroll bars are simple shapes.

Use:  from window_drawing import draw;  draw(app.root, "file.png")
"""
import os
import tempfile
import tkinter as tk
from tkinter import font as tkfont

from PIL import Image, ImageDraw, ImageFont

FONT_DIR = r"C:\Windows\Fonts"
TEXT_COLOUR = (65, 61, 58)
BORDER = (202, 199, 199)


def _font(spec, widget):
    """The Pillow font for a Tk font."""
    f = tkfont.Font(root=widget, font=spec)
    pixels = round(abs(f.actual("size")) * widget.winfo_fpixels("1i") / 72)
    name = "segoeuib.ttf" if f.actual("weight") == "bold" else "segoeui.ttf"
    try:
        return ImageFont.truetype(os.path.join(FONT_DIR, name), max(pixels, 6))
    except OSError:                                       # not Windows: the default font of Pillow
        return ImageFont.load_default()


def _rgb(widget, value):
    if not value:
        return None
    try:
        r, g, b = widget.winfo_rgb(value)
    except tk.TclError:
        return None
    return r // 256, g // 256, b // 256


def _option(widget, name):
    try:
        return widget.cget(name)
    except tk.TclError:
        return None


def _pixels(widget, name):
    """A size option of a widget in pixels (0 if the widget has no such option)."""
    value = _option(widget, name)
    try:
        return widget.winfo_pixels(value) if value not in (None, "") else 0
    except tk.TclError:
        return 0


def _wrap(draw, text, font, width):
    """The lines of a text wrapped at width pixels (0 = no wrap)."""
    lines = []
    for paragraph in str(text).split("\n"):
        line = ""
        for word in paragraph.split(" "):
            trial = (line + " " + word).strip()
            if width and line and draw.textlength(trial, font=font) > width:
                lines.append(line)
                line = word
            else:
                line = trial
        lines.append(line)
    return lines


def _photo(canvas, name):
    """A Tk photo image as a Pillow image (Tk writes it to a PNG file), or None."""
    with tempfile.TemporaryDirectory() as folder:
        file = os.path.join(folder, "image.png")
        try:
            canvas.tk.call(name, "write", file, "-format", "png")
            return Image.open(file).convert("RGB")
        except (tk.TclError, OSError):
            return None


def _canvas_items(image, draw, canvas, x, y):
    for item in canvas.find_all():
        kind, coords = canvas.type(item), canvas.coords(item)
        points = [(coords[i] + x, coords[i + 1] + y) for i in range(0, len(coords) - 1, 2)]
        option = lambda name: canvas.itemcget(item, name) if name in canvas.itemconfigure(item) else ""
        if kind == "image" and option("image"):
            picture = _photo(canvas, option("image"))
            if picture is not None:
                px, py = points[0]
                anchor = option("anchor") or "center"
                left = px - (picture.width / 2 if anchor == "center" else 0)
                top = py - (picture.height / 2 if anchor == "center" else 0)
                image.paste(picture, (int(left), int(top)))
        elif kind == "rectangle":
            no_border = float(option("width") or 1) == 0
            draw.rectangle((*points[0], *points[1]), fill=_rgb(canvas, option("fill")),
                           outline=None if no_border else _rgb(canvas, option("outline")))
        elif kind == "oval":
            draw.ellipse((*points[0], *points[1]), fill=_rgb(canvas, option("fill")),
                         outline=_rgb(canvas, option("outline")), width=2)
        elif kind == "line":
            draw.line(points, fill=_rgb(canvas, option("fill")), width=max(1, int(float(option("width") or 1))))
        elif kind == "text":
            font = _font(option("font") or "TkDefaultFont", canvas)
            anchor = {"w": "lm", "nw": "la", "center": "mm", "e": "rm"}.get(option("anchor"), "lm")
            tx, ty = points[0]
            for line in _wrap(draw, option("text"), font, float(option("width") or 0)):
                draw.text((tx, ty), line, font=font, fill=_rgb(canvas, option("fill")) or TEXT_COLOUR, anchor=anchor)
                ty += font.size * 1.3


def _widget(image, widget, origin):
    """Draw one widget and its children (the children of a canvas: only the part that the canvas shows)."""
    if not widget.winfo_ismapped():
        return
    draw = ImageDraw.Draw(image)
    x, y = widget.winfo_rootx() - origin[0], widget.winfo_rooty() - origin[1]
    w, h = widget.winfo_width(), widget.winfo_height()
    kind = widget.winfo_class()
    background = (255, 255, 255) if kind.startswith("T") else _rgb(widget, _option(widget, "background"))
    if background:
        draw.rectangle((x, y, x + w - 1, y + h - 1), fill=background)
    thickness = _pixels(widget, "highlightthickness")
    if thickness and _rgb(widget, _option(widget, "highlightbackground")):
        draw.rectangle((x, y, x + w - 1, y + h - 1), outline=_rgb(widget, _option(widget, "highlightbackground")),
                       width=thickness)
    if kind in ("Entry", "TCombobox"):
        draw.rectangle((x, y, x + w - 1, y + h - 1), outline=BORDER)
        font = _font(_option(widget, "font") or "TkDefaultFont", widget)
        draw.text((x + 6, y + h / 2), widget.get(), font=font, fill=TEXT_COLOUR, anchor="lm")
        if kind == "TCombobox":
            draw.polygon([(x + w - 16, y + h / 2 - 2), (x + w - 8, y + h / 2 - 2), (x + w - 12, y + h / 2 + 3)],
                         fill=(111, 106, 104))
    if kind in ("Label", "Button") and _option(widget, "text"):
        font = _font(_option(widget, "font"), widget)
        pad = _pixels(widget, "padx") + _pixels(widget, "borderwidth")
        wrap = _pixels(widget, "wraplength")
        lines = _wrap(draw, _option(widget, "text"), font, wrap)
        ty = y + (h - len(lines) * font.size * 1.33) / 2
        for line in lines:
            width = draw.textlength(line, font=font)
            tx = x + pad if _option(widget, "anchor") in ("w", "nw", "sw") else x + (w - width) / 2
            draw.text((tx, ty), line, font=font, fill=_rgb(widget, _option(widget, "foreground")) or TEXT_COLOUR)
            ty += font.size * 1.33
    if kind == "Canvas":
        _canvas_items(image, draw, widget, x, y)
    children = [c for c in widget.winfo_children() if not isinstance(c, tk.Toplevel)]
    if kind == "Canvas" and children:
        layer = image.copy()
        for child in children:
            _widget(layer, child, origin)
        image.paste(layer.crop((x, y, x + w, y + h)), (x, y))
    else:
        for child in children:
            _widget(image, child, origin)


def draw(window, file):
    """Draw a window (Tk or Toplevel) into an image file. No screen capture."""
    window.update_idletasks()                             # the geometry now; no other event runs here
    image = Image.new("RGB", (window.winfo_width(), window.winfo_height()), "white")
    _widget(image, window, (window.winfo_rootx(), window.winfo_rooty()))
    image.save(file)
    return file
