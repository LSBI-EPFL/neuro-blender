"""
The link between the back end and the front end.

The back end (all the logic: the steps, the answers, Blender) sends every question and every message through the
functions of this file. It does not know which front end shows them:
  - the window   (frontends/window.py, the GUI), or
  - the terminal (frontends/terminal.py, the TUI).
main.py selects the front end with use().

A front end gives these functions:
  display:    header, section, note, warn, success, show_path, show_table, stack_drawing, working, progress
  questions:  ask_text, ask_choice, ask_file, ask_yes_no, ask_ticks, ask_colour, pick_file
The other questions of this file (ask, ask_number, ask_layer, ask_layers, ask_materials) use these functions, so
that both front ends check the answers in the same way.

A question returns the answer. If the user goes back (Esc or the Back button), it raises answers.GoBack.
"""
from backend.answers import parse_materials, split_layers

_front = None       # the front end in use (a module with the functions above)

# The 5 steps: (name in the step bar of the front ends, title at the start of the step). The only list of the steps.
STEPS = [("File", "read mask file"), ("Device", "select device"), ("Stack", "build stack"), ("Render", "3D render"),
         ("Labels", "labels")]


def use(front_end):
    """Select the front end: frontends.window or frontends.terminal."""
    global _front
    _front = front_end


# ───────────────────────────────────────────────────────── table cells with a style ──

class Styled(str):
    """A table cell with a style: "faded" (less important) or "alert" (a problem)."""
    style = None


def faded(text):
    cell = Styled(text)
    cell.style = "faded"
    return cell


def alert(text):
    cell = Styled(text)
    cell.style = "alert"
    return cell


# ───────────────────────────────────────────────────────── display ──

def header(step):
    """Show the 5 steps, with the current step, and the title of the step (from STEPS)."""
    _front.header(step, STEPS[step - 1][1])


def steps_with_answers(steps):
    """Tell the front end which steps have saved answers (a list of numbers). The window lets the user click them
    (one way to move: a click on a step opens its answers). A front end with no use for it ignores it."""
    tell = getattr(_front, "steps_with_answers", None)
    if callable(tell):
        tell(steps)


def section(text):
    """Show a title inside a step (example: "Layer 2")."""
    _front.section(text)


def note(text):
    """Show a short note (grey)."""
    _front.note(text)


def warn(text):
    """Show a warning: a problem that the user must know about."""
    _front.warn(text)


def success(text, file=None):
    """Show the end result. file = the result image."""
    _front.success(text, file)


def show_path(label, file, open_now=False):
    """Show a file or a folder. The window also shows the image (or the images of the folder).
    open_now: the terminal opens the image in the image program of the computer."""
    _front.show_path(label, file, open_now)


def show_table(columns, rows, title=None):
    """Show a table. A cell can have a style: faded("text") or alert("text")."""
    _front.show_table(columns, rows, title)


def stack_drawing(layers):
    """Show the stack, top to bottom: one bar in the colour of each material."""
    _front.stack_drawing(layers)


def working(text):
    """Show that the program works. Use: with ui.working("Reading ..."): ..."""
    return _front.working(text)


def progress(text, total):
    """A progress bar. Use: with ui.progress("Rendering", 7) as bar: bar.advance("built 1"); bar.update("text")."""
    return _front.progress(text, total)


# ───────────────────────────────────────────────────────── questions ──

def ask(question, help_text="", default=None, check=None):
    """Ask for a text. check(text) returns an error text, or None when the text is good.
    With a default answer, an empty answer gives the default."""
    return _front.ask_text(question, help_text, default, check)


def ask_number(question, help_text, lowest, highest, default=None):
    """Ask for one whole number from lowest to highest."""
    def check(text):
        if not text.isdigit() or not lowest <= int(text) <= highest:
            return f"Type a number from {lowest} to {highest}."
        return None
    return int(ask(question, help_text, default, check))


def ask_choice(question, help_text, options, default=None, details=None, side=None):
    """Select one option. options = {value: text}. details = {value: help text of the option}.
    side = {value: a short grey text next to the option}. Return the value."""
    return _front.ask_choice(question, help_text, options, default, details or {}, side or {})


def ask_file(question, help_text, options, default=None, details=None, endings=(), browse=None):
    """Select one option, or (window) drop a file on the window. endings = the file endings that a dropped file can
    have (example: (".dxf", ".gds")). browse = the option that opens the file window: the window shows it as a drop
    box ("Drop the file here, or click to select it") above the list, and not in the list.
    Return the value of the option, or the full path of the dropped file."""
    return _front.ask_file(question, help_text, options, default, details or {}, tuple(endings), browse)


def ask_ticks(question, help_text, options, ticked=(), check=None):
    """Tick zero or more options. options = {value: text}. ticked = the values ticked at the start.
    check(selected values) returns an error text, or None (no check: all answers are good, also no tick).
    Return the ticked values, in the order of the options."""
    return _front.ask_ticks(question, help_text, list(options.items()), list(ticked), check or (lambda selected: None),
                            {})


def ask_yes_no(question, help_text="", default="y"):
    """Ask a yes / no question. default = "y" or "n". Return "yes" or "no"."""
    return _front.ask_yes_no(question, help_text, default)


def shape_count(counts):
    """{layer: number of shapes} -> {layer: "4 shapes"}: the grey text next to each mask layer."""
    return {name: f"{n} shape{'s' if n != 1 else ''}" for name, n in (counts or {}).items()}


def ask_layer(layer_names, question, default=None, counts=None, help_text=""):
    """Select one mask layer. counts = {layer: number of shapes}, shown next to each layer. Return the name."""
    return ask_choice(question, help_text, {name: name for name in layer_names},
                      default if default in layer_names else None, side=shape_count(counts))


def ask_layers(layer_names, question, default="", counts=None, none_text=None):
    """Tick one or more mask layers. Return the names as one text ("A, B").

    none_text (example: "no openings") adds a first choice for "none". Then the answer can be "none".
    default: the ticked choices at the start ("A, B", "none", or "" for no tick).
    An answer with no tick is refused: an empty answer is never saved in silence."""
    options = ([("none", none_text)] if none_text else []) + [(name, name) for name in layer_names]
    ticked = ["none"] if (default == "none" and none_text) else [n for n in split_layers(default) if n in layer_names]

    def check(selected):
        if not selected:
            return "Tick at least one box." + (f' None? Tick "{none_text}".' if none_text else "")
        if "none" in selected and len(selected) > 1:
            return f'Untick "{none_text}" or untick mask layers.'
        return None
    selected = _front.ask_ticks(question, "", options, ticked, check, shape_count(counts))
    return "none" if selected == ["none"] else ", ".join(selected)


def ask_materials(question, default=None):
    """Ask for the materials of a layer and their thicknesses, in one line. Return the text in a standard form."""
    def check(text):
        if parse_materials(text) is None:
            return "Write each material and its thickness, with commas between. Example: Ti 25 nm, Pt 150 nm"
        return None
    text = ask(question, "bottom up, with commas. Example: Ti 25 nm, Pt 150 nm, Ti 25 nm", default, check)
    return ", ".join(f"{name} {thickness}" for name, thickness in parse_materials(text))


def ask_colour(question, default=None):
    """Ask for a colour and its transparency. Return "#e3b04b", or "#e3b04b 40%" for a transparent colour."""
    return _front.ask_colour(question, default)


def shows_forms():
    """True when the front end shows the questions of a step as one form (the window), not one at a time.
    The front end tells it with SHOWS_FORMS = True."""
    return getattr(_front, "SHOWS_FORMS", False) is True


def edit_stack(layers, make_questions, problems, open_layer=None):
    """Step 3 as one form. layers = the answers of the layers, from the bottom up: [{question: answer}] with the
    short names of the questions ("name", "type", ...). make_questions(number, layers below) gives the questions
    (backend.questions.Question) of a layer. problems(layers) gives the problems of the stack (texts).
    open_layer = the index of the layer to show open (None: the top layer).
    Return the layers in the same form, with the answers of the necessary questions only."""
    return _front.edit_stack(layers, make_questions, problems, open_layer)


def ask_page(help_text, questions, values):
    """The questions of a page as one form (only a front end with forms). values = the saved answers {key:
    answer}. Return {key: answer} for the necessary questions."""
    return _front.ask_page(help_text, questions, values)


def pick_file(title, start_folder, file_types):
    """Open the usual "open file" window. Return the selected file, or None."""
    return _front.pick_file(title, start_folder, file_types)
