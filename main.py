"""
Neuro Blender: make an exploded-view image of a thin-film implant from its mask file (DXF or GDS).

How to use it:
    python main.py                 opens the window (GUI)
    python main.py --terminal      asks the questions in the terminal (TUI)
    You can add a mask file at the end:  python main.py my_designs/my_implant.gds

The tool has one back end and two front ends:
  - backend/     all the logic: the questions to ask, the answers file, the 3D scene, Blender, the labels.
                 backend/flow.py gives the order of the work. backend/ui.py is the link to the front end.
  - frontends/   only the display and the answers of the user: window.py (GUI) and terminal.py (TUI).
                 Both use the same colours (theme.py) and the same colour window (colour_window.py).

The tool saves all its results in "projects/<name of your mask file>/", and your answers in stack.yaml there.
"""
import os
import sys

from backend import flow, ui
from backend.answers import Stop


def run_in_terminal(mask_file):
    from frontends import terminal
    ui.use(terminal)
    try:
        flow.run(mask_file)
    except KeyboardInterrupt:
        raise SystemExit("\n" + terminal.STOPPED)
    except Stop as problem:                                # a problem that ends the run: show it, then stop
        terminal.warn(str(problem))
        raise SystemExit(1)


def main():
    arguments = sys.argv[1:]
    files = [a for a in arguments if not a.startswith("--")]
    mask_file = os.path.abspath(files[0]) if files else None
    if "--terminal" in arguments:
        run_in_terminal(mask_file)
        return
    try:
        from frontends import window
    except ImportError as error:                       # Tkinter is not installed: use the terminal
        print(f"The window cannot open ({error}). The questions come in the terminal.")
        run_in_terminal(mask_file)
        return
    try:
        window.run(mask_file)
    except window.NoScreen as error:                   # no screen (example: a remote terminal): use the terminal
        print(f"The window cannot open ({error}). The questions come in the terminal.")
        run_in_terminal(mask_file)


if __name__ == "__main__":
    main()
