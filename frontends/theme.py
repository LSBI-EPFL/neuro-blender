"""
The colours and the font of Neuro Blender. The window (GUI) and the terminal (TUI) use the same colours:
the colours of the EPFL graphic charter, red and white, with grey and a blue-green.
"""
RED = "#FF0000"         # EPFL red: the current step, the titles, the main button, the menu pointer
GROSEILLE = "#B51F1F"   # dark red: the steps that are done, the button under the mouse
LEMAN = "#00A79F"       # blue-green: your answers and the "done" messages
CANARD = "#007480"      # dark blue-green: the links to files and folders
TAUPE = "#413D3A"       # dark grey: the text in the window
PERLE = "#CAC7C7"       # light grey: the borders and the steps that come later
GREY = "#827c7b"        # grey: the notes and the help texts in the terminal. The terminal does not tell its
                        # background: this grey has a contrast of 4:1 or more on white and on dark backgrounds
GREY_ON_WHITE = "#6f6a68"   # grey: the notes and the help texts in the window (on a white background)
WHITE = "#FFFFFF"
PANEL = "#F5F4F4"       # very light grey: the background of the question panel in the window

FONTS = ("Segoe UI", "Helvetica Neue", "Helvetica", "Arial")   # the window uses the first font that it finds


def mix(colour, background, amount):
    """Mix two hex colours: amount = 1 gives colour, 0 gives background (Tkinter has no transparent colours)."""
    a = [int(colour[i:i + 2], 16) for i in (1, 3, 5)]
    b = [int(background[i:i + 2], 16) for i in (1, 3, 5)]
    return "#%02x%02x%02x" % tuple(round(amount * x + (1 - amount) * y) for x, y in zip(a, b))
