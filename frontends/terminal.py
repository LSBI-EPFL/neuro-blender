"""
The terminal front end (TUI) of Neuro Blender: everything that the user sees in the terminal.
It gives the functions that backend/ui.py lists. It has no logic of its own: the back end decides what to ask.

  - display:    header (the step bar), section, note, warn, success, show_path, show_table, stack_drawing,
                working, progress;
  - questions:  ask_text, ask_choice, ask_yes_no, ask_ticks, ask_colour, pick_file.

The questions use arrow-key menus (questionary): arrows to move, Enter to confirm, Space to tick, Esc to go back.
In a terminal that cannot show these menus (example: the console of a code editor), the questions change to
typed answers: type the answer, or b to go back.
"""
import os
import sys

from rich.console import Console
from rich.panel import Panel
from rich.progress import BarColumn, Progress, TextColumn, TimeElapsedColumn
from rich.table import Table
from rich.text import Text

from backend.answers import GoBack, GoToStep, join_colour, read_colour, shown
from backend.ui import STEPS
from frontends.desktop import open_on_screen
from frontends.theme import GREY, GROSEILLE, LEMAN, PERLE, RED

console = Console(highlight=False)
BACK = "__go_back__"
GOTO = "__go_to_step__"
STOPPED = "Stopped. Answers saved for next run."


# ───────────────────────────────────────────────────────── display ──

def header(step, title):
    """The step bar: all 5 steps, the current step in white on red."""
    bar = Text()
    for number, (name, _) in enumerate(STEPS, start=1):
        style = f"bold #FFFFFF on {RED}" if number == step else (GROSEILLE if number < step else PERLE)
        bar.append(f" {number} {name} ", style=style)
        bar.append("  ")
    keys = "Esc = back   F1-F5 = go to step   Ctrl+C = stop" if menus() else "b = back   s1-s5 = go to step   Ctrl+C = stop"
    console.print()
    console.print(Panel(bar, title=f"[bold {RED}]Neuro Blender[/]", subtitle=f"[{GREY}]{keys}[/]", border_style=PERLE))
    console.print(Text(f"Step {step}: {title}", style=f"bold {RED}"))


def section(text):
    console.print()
    console.rule(Text(text, style=f"bold {RED}"), style=PERLE)


def note(text):
    console.print(Text(text, style=GREY))


def warn(text):
    console.print(Panel(Text(text), title=f"[bold {RED}]Warning[/]", border_style=RED))


def success(text, file=None):
    body = Text(text, style="bold") + (Text("\n" + file) if file else Text())
    console.print(Panel(body, border_style=LEMAN))


def show_path(label, file, open_now=False):
    """Show a file or a folder. In most terminals, Ctrl+click opens it. open_now: open the file now."""
    file = os.path.abspath(file)
    line = Text(label + " ")
    line.append(file, style=f"link file:///{file.replace(os.sep, '/')}")
    console.print(line)
    if open_now:
        open_on_screen(file)


def _cell(value):
    """A table cell: faded cells in grey, alert cells in red (see backend/ui.py)."""
    style = {"faded": GREY, "alert": RED}.get(getattr(value, "style", None), "")
    return Text(str(value), style=style)


def show_table(columns, rows, title=None):
    table = Table(title=title, title_style="bold", header_style=f"bold {GREY}", border_style=PERLE)
    for column in columns:
        table.add_column(column, justify="right" if column in ("#", "closed", "open", "shapes") else "left")
    for row in rows:
        table.add_row(*[_cell(cell) for cell in row])
    console.print(table)


def working(text):
    """A spinner while the program works. Use: with working("Reading ..."): ..."""
    return console.status(Text(text, style=GREY), spinner="dots")


def stack_drawing(layers):
    """The stack in the terminal, top to bottom: one bar in the real colour of each material."""
    table = Table(show_header=False, box=None, padding=(0, 1))
    for layer in reversed(layers):
        for i, m in enumerate(reversed(layer["materials"])):
            width = 16 if layer["type"] == "electrode coating" else 24
            bar = Text(" " * ((24 - width) // 2)) + Text(" " * width, style=f"on {m['colour']}")   # coatings: centred
            name = Text(f"{m['name']} {shown(m['thickness'])}")
            if m.get("transparency"):
                name.append(f" {m['transparency']}% transparent", style=GREY)
            first = i == 0
            extra = ""
            if first and layer["type"] == "encapsulation":
                openings = "no openings" if layer["openings"] == "none" else f"openings: {layer['openings']}"
                extra = f"{openings}, cleave: {layer['cleave']}"
            table.add_row(bar, name, Text(layer["name"], style="bold") if first else "",
                          Text(layer["type"], style=GREY) if first else "", Text(extra, style=GREY))
    console.print(Panel(table, title="Stack (top to bottom)", border_style=PERLE))


class _Progress:
    """A progress bar (see backend/ui.py): bar.advance(text) = one stage more; bar.update(text) = a new text."""

    def __init__(self, text, total):
        self.bar = Progress(TextColumn("[bold]{task.description}"), BarColumn(complete_style=RED, finished_style=LEMAN),
                            TextColumn("{task.completed}/{task.total}"), TimeElapsedColumn(), console=console)
        self.task = self.bar.add_task(text, total=total)

    def __enter__(self):
        self.bar.__enter__()
        return self

    def __exit__(self, *error):
        return self.bar.__exit__(*error)

    def advance(self, text=None):
        self.bar.update(self.task, advance=1, **({"description": text} if text else {}))

    def update(self, text):
        self.bar.update(self.task, description=text)


def progress(text, total):
    return _Progress(text, total)


# ───────────────────────────────────────────────────────── questions ──

_menus = None


def menus():
    """True if this terminal can show the arrow-key menus."""
    global _menus
    if _menus is None:
        _menus = False
        if sys.stdin.isatty() and sys.stdout.isatty():
            try:
                import questionary  # noqa: F401
                from prompt_toolkit.output.defaults import create_output
                create_output()
                _menus = True
            except Exception:
                pass
    return _menus


def _style():
    from questionary import Style
    return Style([("qmark", f"fg:{RED} bold"), ("question", "bold"), ("pointer", f"fg:{RED} bold"),
                  ("highlighted", f"fg:{RED} bold"), ("selected", f"fg:{RED}"), ("answer", f"fg:{LEMAN} bold"),
                  ("instruction", f"fg:{GREY} italic")])


def _run(question):
    """Ask a questionary question. Esc = go back (GoBack). F1 to F5 = go to that step (GoToStep).
    Ctrl+C = stop the program."""
    from prompt_toolkit.key_binding import KeyBindings, merge_key_bindings
    keys = KeyBindings()

    @keys.add("escape", eager=True)
    def _(event):
        event.app.exit(result=BACK)

    for step in range(1, 6):
        keys.add(f"f{step}", eager=True)(lambda event, n=step: event.app.exit(result=(GOTO, n)))
    question.application.key_bindings = merge_key_bindings([question.application.key_bindings, keys])
    # After Esc, the terminal waits a short time for more keys (an arrow key also starts with Esc). The usual wait
    # is 0.5 s, so Esc felt slow. 0.05 s is enough for the arrow keys.
    question.application.ttimeoutlen = 0.05
    question.application.timeoutlen = 0.05
    result = question.ask()
    if result is None:
        raise SystemExit("\n" + STOPPED)
    if isinstance(result, tuple) and result[:1] == (GOTO,):
        raise GoToStep(result[1])
    if result == BACK:
        raise GoBack
    return result


def _typed(question, help_text="", default=None, check=None):
    """A typed answer (for terminals with no menus). b = go back. s1 to s5 = go to that step."""
    console.print()
    console.print(Text(question, style="bold"))
    if help_text:
        console.print(Text("  " + help_text, style=GREY))
    while True:
        prompt = f"  [Enter = {default}]  (b = back) > " if default is not None else "  (b = back) > "
        text = input(prompt).strip()
        if text.lower() == "b":
            raise GoBack
        if text.lower() in ("s1", "s2", "s3", "s4", "s5"):
            raise GoToStep(int(text[1]))
        text = text or ("" if default is None else str(default))
        if not text:
            console.print("  Type an answer, then push Enter.")
            continue
        error = check(text) if check else None
        if error:
            console.print(Text("  " + error, style="yellow"))
            continue
        return text


def ask_text(question, help_text="", default=None, check=None):
    """Ask for a text. check(text) returns an error text, or None when the text is good.

    The answer field starts empty. With a default answer, the grey help text shows "Enter = <default>", and Enter
    alone gives the default. (A field that starts with the default typed in it adds new letters after it.)"""
    if not menus():
        return _typed(question, help_text, default, check)
    import questionary

    def validate(text):
        text = text.strip()
        if not text:
            return True if default is not None else "Type an answer, then push Enter."
        return (check(text) if check else None) or True
    parts = ([help_text] if help_text else []) + ([f"Enter = {default}"] if default is not None else [])
    text = _run(questionary.text(question, instruction=f"({'.  '.join(parts)})" if parts else None,
                                 validate=validate, style=_style())).strip()
    return text or str(default)


def _title(text, side):
    """The text of one choice, with a grey side text in a column (example: "4 shapes")."""
    return [("", f"{text:<28}"), ("class:instruction", side)] if side else text


def ask_choice(question, help_text, options, default=None, details=None, side=None):
    """Select one option. options = {value: text}. details = {value: help text, shown for the selected option}.
    side = {value: short grey text next to the option}."""
    details, side = details or {}, side or {}
    if not menus():                                    # typed: the number of the option (or its name)
        keys = list(options)

        def line(n, key):
            text = options[key] if options[key].startswith(f"{n} ") else f"{n} = {options[key]}"   # no "1 = 1 ..."
            return text + (f"  ({side[key]})" if key in side else "") + (f"  {details[key]}" if key in details else "")

        def to_key(text):
            if text.isdigit() and 1 <= int(text) <= len(keys):
                return keys[int(text) - 1]
            return text if text in options else None
        lines = ([help_text] if help_text else []) + [line(n, key) for n, key in enumerate(keys, start=1)]
        text = _typed(question, "\n  ".join(lines), keys.index(default) + 1 if default in keys else None,
                      lambda t: None if to_key(t) is not None else f"Type a number from 1 to {len(keys)}.")
        return to_key(text)
    import questionary
    choices = [questionary.Choice(title=_title(text, side.get(value)), value=value, description=details.get(value))
               for value, text in options.items()]
    return _run(questionary.select(question, choices=choices, default=default if default in options else None,
                                   instruction=f"({help_text})" if help_text else None, style=_style()))


def ask_file(question, help_text, options, default=None, details=None, endings=(), browse=None):
    """Select one option. A terminal cannot take a dropped file, so this is the same as ask_choice."""
    return ask_choice(question, help_text, options, default, details)


def ask_yes_no(question, help_text="", default="y"):
    """Ask a yes / no question. Return "yes" or "no"."""
    if not menus():
        text = _typed(question + " (y / n)", help_text, default,
                      lambda t: None if t.lower() in ("y", "yes", "n", "no") else "Type y (yes) or n (no).")
        return "yes" if text.lower() in ("y", "yes") else "no"
    import questionary
    if help_text:
        note(help_text)
    return "yes" if _run(questionary.confirm(question, default=default == "y", style=_style())) else "no"


def ask_ticks(question, help_text, options, ticked, check, side=None):
    """Tick one or more options. options = [(value, text)]. ticked = the values ticked at the start.
    check(selected values) returns an error text, or None. Return the selected values, in the order of the options.
    In typed mode, an option with the value "none" has the number 0."""
    side = side or {}
    values = [value for value, _ in options]
    if not menus():
        first = 0 if values and values[0] == "none" else 1
        numbers = {value: n for n, value in enumerate(values, start=first)}
        lines = [f"{numbers[value]} = {text}" + (f"  ({side[value]})" if value in side else "") for value, text in options]

        def to_values(text):
            parts = text.split()
            if not parts or not all(p.isdigit() and first <= int(p) < first + len(values) for p in parts):
                return None
            return [value for value in values if str(numbers[value]) in parts]

        def check_typed(text):
            chosen = to_values(text)
            if chosen is None:
                return f"Type numbers from {first} to {first + len(values) - 1}, with spaces between."
            return check(chosen)
        default = " ".join(str(numbers[v]) for v in values if v in ticked) or None
        text = _typed(question, (help_text + "\n  " if help_text else "") +
                      "Type one or more numbers, with spaces between. Example: 3 5\n  " + "\n  ".join(lines),
                      default, check_typed)
        return to_values(text)
    import questionary
    choices = [questionary.Choice(_title(text, side.get(value)), value=value, checked=value in ticked)
               for value, text in options]
    selected = _run(questionary.checkbox(question, choices=choices, style=_style(),
                                         validate=lambda chosen: check(chosen) or True,
                                         instruction="(Space = tick or untick, Enter = confirm)"))
    return [value for value in values if value in selected]


def ask_colour(question, default=None):
    """Ask for a colour: a name ("gold"), a hex code ("#e3b04b"), or "p" for the colour window (colour and
    transparency). Return "#e3b04b", or "#e3b04b 40%" for a transparent colour. A block in the colour shows after
    the answer."""
    def check(text):
        return None if text.lower() == "p" or read_colour(text) else \
            "Type colour name (gold), hex code (#e3b04b) or p for colour window."
    while True:
        text = ask_text(question, "name or hex code (gold, #e3b04b).  p = colour window with transparency",
                        default, check)
        if text.lower() == "p":
            picked = pick_colour_window(*(read_colour(default or "") or ("#808080", 0)))
        else:
            picked = read_colour(text)
        if picked:
            colour, transparency = picked
            line = Text("   ") + Text("      ", style=f"on {colour}")
            line.append(f"  {colour}{f', {transparency}% transparent' if transparency else ''}", style=GREY)
            console.print(line)
            return join_colour(colour, transparency)
        note("  No colour selected.")


# ───────────────────────────────────────────────────────── pop-up windows ──

def pick_file(title, start_folder, file_types):
    """Open the usual "open file" window. Return the selected file, or None (cancelled or no window)."""
    note("Window opens now. It can be behind this terminal.")
    try:
        import tkinter as tk
        from tkinter import filedialog
        root = tk.Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        file = filedialog.askopenfilename(parent=root, title=title, initialdir=start_folder, filetypes=file_types)
        root.destroy()
        return file or None
    except Exception as error:                          # no screen, or Tkinter is not installed
        note(f"  Pop-up window cannot open ({error}).")
        return None


def pick_colour_window(start_colour="#808080", start_transparency=0):
    """Open the colour window (frontends/colour_window.py): the colour and its transparency.
    Return (hex code, transparency in %), or None (cancelled or no window)."""
    try:
        from frontends.colour_window import ColourWindow
        return ColourWindow(start_colour, start_transparency).run()
    except Exception as error:
        note(f"  Pop-up window cannot open ({error}).")
        return None
