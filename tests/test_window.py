"""
Test the questions of the window front end (GUI) with simulated keys and clicks. The window opens for some
seconds and closes by itself.

Run:  python tests/test_window.py
      python tests/test_window.py --screenshots <folder>     also saves an image of each question (drawn from the
                                                             widgets: no screen capture)
Each line shows PASS or FAIL. At the end, the script shows the number of failures.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend import ui
from backend.answers import GoBack, GoToStep
from frontends import window

SCREENSHOTS = sys.argv[sys.argv.index("--screenshots") + 1] if "--screenshots" in sys.argv else None


def entry(app):
    """The text field of the question that is open now."""
    stack = list(app.q_body.winfo_children())
    while stack:
        widget = stack.pop(0)
        if widget.winfo_class() == "Entry":
            return widget
        stack += widget.winfo_children()


def type_text(text):
    def act(app):
        field = entry(app)
        field.delete(0, "end")
        field.insert(0, text)
    return act


def press(*names):
    def act(app):
        for name in names:
            if name == "Next":
                app.next()
            elif name == "Back":
                app.back()
            else:
                app.keys[name]()
    return act


def click(text):
    """Click the button with this text in the question panel."""
    def act(app):
        stack = list(app.q_body.winfo_children())
        while stack:
            widget = stack.pop(0)
            if isinstance(widget, window.FlatButton) and widget.cget("text") == text:
                widget.command()
                return
            stack += widget.winfo_children()
    return act


def click_step(step):
    """Click a step in the step list (left)."""
    def act(app):
        app.go_to_step(step)
    return act


def stack_form(*layers):
    """Open the form of step 3 with these layers (the questions and the rules of the back end)."""
    from backend.step3_layer_questions import check_stack, form_questions
    names = ["OUTLINE", "METAL", "OPENINGS"]
    return ui.edit_stack([dict(layer) for layer in layers],
                         lambda number, below: form_questions(number, below, names, {}, "OUTLINE"),
                         lambda values: check_stack([{"type": v.get("type")} for v in values]))


PI = {"name": "Bottom PI", "type": "encapsulation", "shape": "OUTLINE", "materials": "PI 5 um", "colours": "#d99a2b",
      "openings": "none", "cleave": "yes"}
TRACKS = {"name": "Tracks", "type": "tracks", "shape": "METAL", "materials": "Ti 20 nm, Au 200 nm",
          "colours": "#8c857b, #e3b04b", "surface": "shiny"}


def form_value(name, value):
    """Change a field of the open card of the form."""
    def act(app):
        field = app.form.fields[name]
        if hasattr(field, "variable"):
            field.variable.set(value)
        elif hasattr(field, "values"):
            field.widget.current(field.values.index(value))
            field.chosen()
        else:
            field.pick(value)
    return act


def page_form():
    """A page form with the questions of step 4 before the 3D build."""
    from backend.questions import Question
    return ui.ask_page("Values for the 3D shapes.", [
        Question("render view", "choice", "Which part?", options={"electrodes": "Electrodes", "whole device": "Whole"},
                 default="electrodes", label="Part of the device"),
        Question("render cleave angle", "number", "Cleave angle?", "0 = flat", options=(0, 45), default="9",
                 label="Cleave angle (degrees, 0 to 45)"),
        Question("render space between layers", "number", "Space?", options=(0, 100),
                 default=lambda values: "0" if values.get("render cleave angle") != "0" else "30",
                 label="Space between layers")], {})


def page_value(key, value):
    def act(app):
        app.form.fields[key].variable.set(value)
    return act


def form_do(method, *args):
    return lambda app: getattr(app.form, method)(*args)


class DropEvent:
    """The event of a file dropped on the window (tkinterdnd2 puts a path with spaces in braces)."""
    def __init__(self, path):
        self.data, self.action = "{" + path + "}", "copy"


def drop(path):
    """Drop a file on the window."""
    return lambda app: app.dropped(DropEvent(path))


def answer_can_drop(app):
    """Answer the open text question with "yes" if the window takes dropped files."""
    type_text("yes" if app.can_drop else "no")(app)
    app.next()


MASK_FILES = {"probe.dxf": "probe.dxf", "window": "Find the file in a window ..."}


def messages_with_table():
    """Many lines of messages with a table in the middle, then a question (the back end side)."""
    for n in range(30):
        ui.note(f"Line {n + 1} of the messages.")
    ui.show_table(["#", "name"], [["1", "Bottom PI"], ["2", "Tracks"]], title="A table in the messages")
    for n in range(30):
        ui.note(f"Line {n + 31} of the messages.")
    return ui.ask("Did the messages scroll?", "", "")


def wheel_on_table():
    """Turn the mouse wheel up one step on the table in the messages. Type "scrolled" if the messages scroll."""
    def act(app):
        app.come_to_front()                                  # the wheel goes to the widget under the mouse
        table = [w for w in app.log.winfo_children() if w.winfo_class() == "Frame"][-1]
        app.log.see(str(table))
        app.root.update()
        cell = table.winfo_children()[0]
        before = app.log.yview()[0]
        cell.event_generate("<MouseWheel>", delta=120, rootx=cell.winfo_rootx() + 2, rooty=cell.winfo_rooty() + 2,
                            when="now")
        field = entry(app)
        field.delete(0, "end")
        field.insert(0, "scrolled" if app.log.yview()[0] < before else "not scrolled")
        app.next()
    return act


# (name, the question, the actions of the robot, the expected answer)
TESTS = [
    ("stack form: change a thickness in the open layer, then Next", lambda: stack_form(PI, TRACKS),
     [form_value("materials", "Ti 20 nm, Au 300 nm"), press("Next")],
     [PI, dict(TRACKS, materials="Ti 20 nm, Au 300 nm")]),
    ("stack form: a layer with no colour is refused; a colour, then Next",
     lambda: stack_form(PI, TRACKS),
     [form_value("materials", "Ti 20 nm, Pt 150 nm"), press("Next"),
      lambda app: (app.form.colours[1].update(Pt="#c9c7c2"), app.form.build()), press("Next")],
     [PI, dict(TRACKS, materials="Ti 20 nm, Pt 150 nm", colours="#8c857b, #c9c7c2")]),
    ("stack form: a new layer on top, from the default answers",
     lambda: stack_form(PI),
     [form_do("add_layer"), form_value("name", "Tracks"), form_value("type", "tracks"), form_value("shape", "METAL"),
      form_value("materials", "Au 200 nm"), lambda app: app.form.colours[1].update(Au="#e3b04b"), press("Next")],
     [PI, {"name": "Tracks", "type": "tracks", "shape": "METAL", "materials": "Au 200 nm", "colours": "#e3b04b",
           "surface": "shiny"}]),
    ("stack form: a colour picked in a lower layer is the default colour of the same material in a new layer",
     lambda: stack_form(PI, TRACKS),
     [lambda app: app.form.colours[1].update(Au="#123456"), form_do("add_layer"), form_value("name", "Coating"),
      form_value("type", "electrode coating"), form_value("shape", "METAL"), form_value("materials", "Au 200 nm"),
      press("Next"), press("Back")],                    # (Back only if Next is refused: then the test fails, no wait)
     [PI, dict(TRACKS, colours="#8c857b, #123456"),
      {"name": "Coating", "type": "electrode coating", "shape": "METAL", "materials": "Au 200 nm",
       "colours": "#123456", "surface": "shiny"}]),
    ("stack form: Back goes back", lambda: stack_form(PI, TRACKS), [press("Back")], "GoBack"),
    ("drop: the window takes dropped files (package tkinterdnd2)", lambda: ui.ask("Drop?", "", ""),
     [answer_can_drop], "yes"),
    ("drop: a dropped mask file is the answer (its full path)",
     lambda: ui.ask_file("Which mask file?", "", MASK_FILES, endings=(".dxf", ".gds")),
     [drop("C:/My Designs/implant.dxf"), press("Next")], os.path.abspath("C:/My Designs/implant.dxf")),
    ("drop: a file of another type is refused; then a choice in the list",
     lambda: ui.ask_file("Which mask file?", "", MASK_FILES, endings=(".dxf", ".gds")),
     [drop("C:/photo.png"), press("Down", "Next")], "window"),
    ("drop box: a click on the box is the choice that opens the file window",
     lambda: ui.ask_file("Which mask file?", "", MASK_FILES, endings=(".dxf", ".gds"), browse="window"),
     [lambda app: app.drop_box.click()], "window"),
    ("drop box: the list does not show the choice of the file window",
     lambda: ui.ask_file("Which mask file?", "", MASK_FILES, endings=(".dxf", ".gds"), browse="window"),
     [press("Down", "Next")], "probe.dxf"),
    ("drop box: a file dropped on the box is the answer",
     lambda: ui.ask_file("Which mask file?", "", MASK_FILES, endings=(".dxf", ".gds"), browse="window"),
     [drop("C:/implant.dxf")], os.path.abspath("C:/implant.dxf")),
    ("drop: a question that takes no file refuses a dropped file", lambda: ui.ask("Name?", "", "Top PI"),
     [drop("C:/implant.dxf"), press("Next")], "Top PI"),
    ("page form: a number out of range is refused; a good number, then Next", lambda: page_form(),
     [page_value("render cleave angle", "60"), press("Next"), page_value("render cleave angle", "12"), press("Next")],
     {"render view": "electrodes", "render cleave angle": "12", "render space between layers": "0"}),
    ("steps: a click on step 2 goes to step 2", lambda: ui.ask("Name?", "", "Top PI"), [click_step(2)], "GoToStep 2"),
    ("steps: a click on a later step does nothing", lambda: ui.ask("Name?", "", "Top PI"),
     [click_step(5), press("Next")], "Top PI"),
    ("steps: a click on a later step with saved answers goes to it",
     lambda: (ui.steps_with_answers([1, 2, 3, 4]), ui.ask("Name?", "", "Top PI"))[1], [click_step(4)], "GoToStep 4"),
    ("messages: the mouse wheel on a table in the messages scrolls the messages", messages_with_table,
     [wheel_on_table()], "scrolled"),
    ("text: Next keeps the default", lambda: ui.ask("Name?", "it shows on the image", "Top PI"),
     [press("Next")], "Top PI"),
    ("text: a typed answer", lambda: ui.ask("Name?", "", "5/0"), [type_text("Pads"), press("Next")], "Pads"),
    ("text: Back goes back", lambda: ui.ask("Name?"), [press("Back")], "GoBack"),
    ("text: a bad answer is refused", lambda: ui.ask_materials("Materials?"),
     [type_text("Ti/Pt"), press("Next"), type_text("Ti 25 nm, Pt 150 nm"), press("Next")], "Ti 25 nm, Pt 150 nm"),
    ("list: arrow down, then Next", lambda: ui.ask_choice("Type?", "", {"a": "encapsulation", "b": "tracks"},
                                                          details={"a": "A polymer layer.", "b": "The metal lines."}),
     [press("Down", "Next")], "b"),
    ("list: Next keeps the default", lambda: ui.ask_choice("Type?", "", {"a": "a", "b": "b"}, default="b"),
     [press("Next")], "b"),
    ("mask layer: default, with the shape counts",
     lambda: ui.ask_layer(["OUTLINE", "METAL", "OPENINGS"], "Shape: which mask layer draws this layer?",
                          default="METAL", counts={"OUTLINE": 1, "METAL": 9, "OPENINGS": 12}),
     [press("Next")], "METAL"),
    ("boxes: no tick is refused, then tick 'no openings'",
     lambda: ui.ask_layers(["OUTLINE", "METAL", "OPENINGS_ELECTRODES", "OPENINGS_PADS"],
                           "Openings in the Top PI: which mask layers draw them?",
                           counts={"OUTLINE": 1, "METAL": 9, "OPENINGS_ELECTRODES": 8, "OPENINGS_PADS": 8},
                           none_text="no openings"),
     [press("Next"), press("space", "Next")], "none"),
    ("boxes: tick two mask layers",
     lambda: ui.ask_layers(["A", "B", "C"], "Openings?", none_text="no openings"),
     [press("Down", "Down", "space", "Down", "space", "Next")], "B, C"),
    ("boxes: 'no openings' with a mask layer is refused",
     lambda: ui.ask_layers(["A", "B"], "Openings?", default="none", none_text="no openings"),
     [press("Down", "space", "Next"), press("Up", "space", "Next")], "A"),
    ("boxes: a long list scrolls (16 mask layers)",
     lambda: ui.ask_layers([f"LAYER_{n:02d}" for n in range(1, 17)], "Which mask layers draw the through holes?",
                           counts={f"LAYER_{n:02d}": n for n in range(1, 17)}, none_text="no through holes"),
     [press(*["Down"] * 14, "space", "Next")], "LAYER_14"),
    ("yes / no: n", lambda: ui.ask_yes_no("Cleave this layer?", "A cleaved layer bends away from the tracks."),
     [press("n")], "no"),
    ("yes / no: Next keeps the default", lambda: ui.ask_yes_no("Add a layer on top?"), [press("Next")], "yes"),
    ("colour: a name with a transparency", lambda: ui.ask_colour("Colour of the PI?"),
     [type_text("gold 40%"), press("Next")], "#ffd700 40%"),
    ("colour: the colour window gives the colour and the transparency", lambda: ui.ask_colour("Colour of the PDMS?"),
     [click("Colour window ..."), press("Next")], "#3366cc 40%"),
    ("colour: a bad colour is refused", lambda: ui.ask_colour("Colour of the Pt?", "#c9c7c2"),
     [type_text("not a colour"), press("Next"), type_text("#c9c7c2"), press("Next")], "#c9c7c2"),
]


def screenshot(app, name):
    """Save an image of the test window. No screen capture: the image is drawn from the widgets
    (tests/window_drawing.py), so it can never show another window of the user."""
    from window_drawing import draw
    draw(app.root, os.path.join(SCREENSHOTS, "".join(c if c.isalnum() else "_" for c in name)[:60] + ".png"))


COLOUR_WINDOW_SIZES = []          # (field size, check size) of each colour window that the robot used


def automatic_colour_window():
    """In the colour window, the robot types a hex code, sets 40 % transparency and pushes OK."""
    from frontends import colour_window
    original_run = colour_window.ColourWindow.run

    def run(self):
        COLOUR_WINDOW_SIZES.append((self.size, self.check))
        def act():
            self.hex_text.set("#3366cc")
            self.typed_hex()
            self.transparency.set(40)
            self.show()
            if SCREENSHOTS:
                from window_drawing import draw
                draw(self.root, os.path.join(SCREENSHOTS, "colour_window_in_the_window.png"))
            self.ok()
        self.root.after(400, act)
        return original_run(self)
    colour_window.ColourWindow.run = run
    return lambda: setattr(colour_window.ColourWindow, "run", original_run)     # puts the old function back


def main():
    put_back_colour_window = automatic_colour_window()
    window._app = app = window.App()
    ui.use(window)
    results, robot = [], {"actions": []}
    original_open = window.App.open_question

    def open_question(self, *args, **kwargs):              # after each question opens: the robot acts
        original_open(self, *args, **kwargs)
        if robot["actions"]:
            action = robot["actions"].pop(0)
            self.root.after(200, lambda: run_action(action))

    def run_action(action):
        if SCREENSHOTS and robot["first"]:
            screenshot(app, robot["name"])
            robot["first"] = False
        reply = app.reply
        action(app)
        if app.reply is reply and robot["actions"]:          # the question stays open (example: a refused answer)
            app.root.after(150, lambda: run_action(robot["actions"].pop(0)))
    window.App.open_question = open_question

    def back_end():                                          # the back end thread: ask the test questions
        ui.header(3)
        ui.note("These questions are a test of the window.")
        for name, question, actions, expected in TESTS:
            robot.update(actions=list(actions), name=name, first=True)
            try:
                result = question()
            except GoBack:
                result = "GoBack"
            except GoToStep as jump:
                result = f"GoToStep {jump.step}"
            results.append((name, result, expected))
        app.calls.put(("test_done", (), None))

    def done():
        app.closed = True
        app.root.destroy()
    app.do_test_done = done
    import threading
    threading.Thread(target=back_end, daemon=True).start()
    app.root.after(30, app.poll)
    app.root.mainloop()
    window.App.open_question = original_open                  # put back the replaced functions
    put_back_colour_window()

    # One more check: each colour window keeps its sizes (scaled for the screen); the module sizes do not change.
    from frontends import colour_window
    results.append(("colour window: its sizes are on the window, the module sizes stay",
                    bool(COLOUR_WINDOW_SIZES) and (colour_window.FIELD, colour_window.CHECK) == (240, 12)
                    and all(f >= 240 and c >= 12 for f, c in COLOUR_WINDOW_SIZES), True))
    total = len(TESTS) + 1

    failures = 0
    for name, result, expected in results:
        ok = result == expected
        failures += not ok
        print(f"{'PASS' if ok else 'FAIL'}  {name}" + ("" if ok else f"   (expected {expected!r}, got {result!r})"))
    missing = total - len(results)
    print(f"\n{len(results) - failures} of {total} tests pass." + (f" {missing} did not run." if missing else ""))
    sys.exit(1 if failures or missing else 0)


if __name__ == "__main__":
    main()
