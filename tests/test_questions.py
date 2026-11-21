"""
Test the questions of the terminal front end (the menus) with simulated key presses. No real terminal is necessary.

Run:  python tests/test_questions.py
Each line shows PASS or FAIL. At the end, the script shows the number of failures.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import questionary
from prompt_toolkit.input import create_pipe_input
from prompt_toolkit.output import DummyOutput

from backend import ui
from backend.answers import GoBack, GoToStep
from frontends import terminal

ui.use(terminal)                                  # these tests check the terminal front end
terminal._menus = True                            # use the menus, also when this is not a real terminal
DOWN, ENTER, SPACE, ESC, BACKSPACE = "\x1b[B", "\r", " ", "\x1b", "\x08"


def answer_with_keys(question_function, keys):
    """Run one question with the simulated keys. Return its answer, or "GoBack" after Esc."""
    with create_pipe_input() as keyboard:
        keyboard.send_text(keys)
        originals = {name: getattr(questionary, name) for name in ("text", "select", "checkbox", "confirm")}
        for name, function in originals.items():
            setattr(questionary, name, (lambda f: lambda *a, **k: f(*a, input=keyboard, output=DummyOutput(), **k))(function))
        try:
            return question_function()
        except GoBack:
            return "GoBack"
        except GoToStep as jump:
            return f"GoToStep {jump.step}"
        finally:
            for name, function in originals.items():
                setattr(questionary, name, function)


TESTS = [
    ("text: Enter keeps the default", lambda: ui.ask("Name?", "", "5/0"), ENTER, "5/0"),
    ("text: a typed answer", lambda: ui.ask("Name?", "", "5/0"), "Pads" + ENTER, "Pads"),
    ("text: Esc goes back", lambda: ui.ask("Name?"), ESC, "GoBack"),
    ("list: arrow down, then Enter", lambda: ui.ask_choice("Type?", "", {"a": "a", "b": "b", "c": "c"}),
     DOWN + ENTER, "b"),
    ("list: Enter keeps the default", lambda: ui.ask_choice("Type?", "", {"a": "a", "b": "b"}, default="b"),
     ENTER, "b"),
    ("list: Esc goes back", lambda: ui.ask_choice("Type?", "", {"a": "a"}), ESC, "GoBack"),
    ("mask layer: default", lambda: ui.ask_layer(["A", "B"], "Shape?", default="B", counts={"A": 1, "B": 4}),
     ENTER, "B"),
    ("boxes: tick the first and the third", lambda: ui.ask_layers(["A", "B", "C"], "Openings?"),
     SPACE + DOWN + DOWN + SPACE + ENTER, "A, C"),
    ("boxes: Enter with no tick is refused", lambda: ui.ask_layers(["A", "B"], "Openings?"),
     ENTER + SPACE + ENTER, "A"),
    ("boxes: old answer is ticked", lambda: ui.ask_layers(["A", "B"], "Openings?", default="B"), ENTER, "B"),
    ("boxes: 'no openings' ticked at the start, Enter keeps it",
     lambda: ui.ask_layers(["A", "B"], "Openings?", default="none", none_text="no openings"), ENTER, "none"),
    ("boxes: 'no openings' with a mask layer is refused",
     lambda: ui.ask_layers(["A", "B"], "Openings?", default="none", none_text="no openings"),
     DOWN + SPACE + ENTER + "\x1b[A" + SPACE + ENTER, "A"),
    ("boxes: no tick is refused, then tick 'no openings'",
     lambda: ui.ask_layers(["A", "B"], "Openings?", none_text="no openings"), ENTER + SPACE + ENTER, "none"),
    ("yes / no: n", lambda: ui.ask_yes_no("Cleave?"), "n", "no"),
    ("yes / no: Esc goes back", lambda: ui.ask_yes_no("Cleave?"), ESC, "GoBack"),
    ("steps: F3 goes to step 3", lambda: ui.ask("Name?", "", "Top PI"), "\x1bOR", "GoToStep 3"),
    ("steps: F2 goes to step 2 from a list", lambda: ui.ask_choice("Type?", "", {"a": "a", "b": "b"}), "\x1bOQ",
     "GoToStep 2"),
    ("boxes: Esc goes back", lambda: ui.ask_layers(["A", "B"], "Openings?", none_text="no openings"), ESC, "GoBack"),
    ("mask layer: Esc goes back", lambda: ui.ask_layer(["A", "B"], "Shape?"), ESC, "GoBack"),
    ("colour: Esc goes back", lambda: ui.ask_colour("Colour?", "#8c857b"), ESC, "GoBack"),
    ("materials: a bad text is refused", lambda: ui.ask_materials("Materials?"),
     "Ti/Pt" + ENTER + BACKSPACE * 5 + "Ti 25 nm, Pt 150 nm" + ENTER, "Ti 25 nm, Pt 150 nm"),
    ("colour: a name", lambda: ui.ask_colour("Colour?"), "gold" + ENTER, "#ffd700"),
    ("colour: Enter keeps the default", lambda: ui.ask_colour("Colour?", "#8c857b"), ENTER, "#8c857b"),
    ("colour: a name with a transparency", lambda: ui.ask_colour("Colour?"), "gold 40%" + ENTER, "#ffd700 40%"),
    ("colour: Enter keeps a transparent default", lambda: ui.ask_colour("Colour?", "#d99a2b 40%"), ENTER,
     "#d99a2b 40%"),
    ("colour: a transparency above 90 % is refused", lambda: ui.ask_colour("Colour?"),
     "gold 95%" + ENTER + BACKSPACE * 3 + "30%" + ENTER, "#ffd700 30%"),
]

failures = 0
for name, question, keys, expected in TESTS:
    result = answer_with_keys(question, keys)
    ok = result == expected
    failures += not ok
    print(f"{'PASS' if ok else 'FAIL'}  {name}" + ("" if ok else f"   (expected {expected!r}, got {result!r})"))
print(f"\n{len(TESTS) - failures} of {len(TESTS)} tests pass.")
sys.exit(1 if failures else 0)
