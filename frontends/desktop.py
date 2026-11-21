"""
Two actions on the computer that both front ends use: sharp windows with display scaling, and open a file in its
usual program.
"""
import os
import subprocess
import sys


def sharp_on_windows():
    """On Windows with display scaling (example: 150 %), tell Windows that this program scales itself.
    With no call, Windows enlarges the windows as an image, and they are not sharp."""
    if sys.platform == "win32":
        try:
            import ctypes
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except Exception:
            pass


def open_on_screen(file):
    """Open a file or a folder in the usual program of the computer (example: an image in the image program)."""
    try:
        if sys.platform.startswith("win"):
            os.startfile(file)
        else:
            subprocess.Popen(["open" if sys.platform == "darwin" else "xdg-open", file])
    except Exception:
        pass
