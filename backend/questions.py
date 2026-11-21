"""
Questions as data (review finding CR-07). A step makes Question objects; a front end shows them.

A Question has its key in the answers, its kind, its text, its default answer, its check and the condition that
makes it necessary. The same objects serve two ways to show them:
  - one question at a time (ask(), answer_all()): the terminal, and the window for the steps with no form;
  - one form with all the questions of a step: the window (frontends/stack_form.py for step 3).
So a question, its check and its default are written one time, in the back end.

The kinds:
  text        a short text                           (example: the name of a layer)
  choice      one of the options {value: text}
  yes/no      "yes" or "no"
  layer       one mask layer of options (a list of names), with counts = {name: number of shapes}
  layers      ticks of mask layers, "A, B"; with none_text, also "none" (example: "no openings")
  number      a number from options[0] to options[1] (decimals are OK)
  materials   materials and thicknesses, "Ti 20 nm, Au 200 nm"
  colours     one colour for each different material of the answer of materials_key, "#8c857b, #e3b04b 40%"
"""
from dataclasses import dataclass
from typing import Callable

from backend import answers, ui
from backend.answers import answer, parse_materials, read_colour, split_layers

MATERIALS_EXAMPLE = "Write each material and its thickness, with commas between. Example: Ti 25 nm, Pt 150 nm"


@dataclass
class Question:
    key: str                          # the key of the answer (example: "layer 3 name")
    kind: str                         # one of the kinds above
    text: object                      # the question: a text, or a function of the page answers that gives it
    help: str = ""
    options: object = None            # choice: {value: text}. layer, layers: the list of mask layer names
    details: dict = None              # choice: {value: help text of the option}
    counts: dict = None               # layer, layers: {mask layer: number of shapes}
    none_text: str = None             # layers: the text of the "none" choice
    default: object = None            # the default answer (colours: {material: colour}), or a function of the page
                                      # answers that gives it
    needed: Callable = lambda values: True     # True when the question is necessary (values = page answers)
    materials_key: str = None         # colours: the key of the materials answer in the same page
    label: str = ""                   # a short name of the answer, for a field of a form (example: "Mask layer")

    def title(self, values):
        """The text of the question, for the answers of its page so far."""
        return self.text(values) if callable(self.text) else self.text

    def initial(self, values):
        """The default answer, for the answers of its page so far."""
        return self.default(values) if callable(self.default) else self.default

    def check(self, value, values=None):
        """The problem of an answer (a short text), or None when the answer is good.
        values = the answers of the page (colours: the materials)."""
        value = "" if value is None else str(value)
        if self.kind in ("text", "materials", "colours") and not value.strip():
            return "Type an answer."
        if self.kind == "choice" and value not in self.options:
            return "Select one option."
        if self.kind == "yes/no" and value not in ("yes", "no"):
            return "Select yes or no."
        if self.kind == "layer" and value not in self.options:
            return "Select one mask layer."
        if self.kind == "layers":
            if value == "none":
                return None if self.none_text else "Tick at least one box."
            names = split_layers(value)
            if not names:
                return "Tick at least one box." + (f' None? Tick "{self.none_text}".' if self.none_text else "")
            if "none" in names:
                return f'Untick "{self.none_text}" or untick mask layers.'
            if any(name not in self.options for name in names):
                return "Tick only mask layers of the list."
        if self.kind == "number":
            lowest, highest = self.options
            message = f"Type a number from {lowest:g} to {highest:g}."
            try:
                return None if lowest <= float(value) <= highest else message
            except ValueError:
                return message
        if self.kind == "materials" and parse_materials(value) is None:
            return MATERIALS_EXAMPLE
        if self.kind == "colours":
            materials = parse_materials((values or {}).get(self.materials_key, "")) or []
            colours = [c.strip() for c in value.split(",")]
            if len(colours) != len(materials) or not all(read_colour(c) for c in colours):
                return "Give one colour for each material."
        return None


def colour_names(materials_text):
    """The different materials of a materials answer, in their order (Ti in Ti / Pt / Ti: one time)."""
    names = []
    for name, _ in parse_materials(materials_text) or []:
        if name not in names:
            names.append(name)
    return names


def ask_colours(materials_text, defaults):
    """Ask one colour for each different material. defaults = {material: colour}. Return "#aaa, #bbb 40%", with
    one colour for each material of the answer (a material two times in the layer gets one question)."""
    chosen = {name: ui.ask_colour(f"Colour of {name}?", (defaults or {}).get(name))
              for name in colour_names(materials_text)}
    return ", ".join(chosen[name] for name, _ in parse_materials(materials_text))


def ask(question, values):
    """Ask one question with the questions of backend/ui.py (one question at a time). Return the answer text."""
    q, text, default = question, question.title(values), question.initial(values)
    if q.kind == "text":
        return ui.ask(text, q.help, default)
    if q.kind == "number":
        return ui.ask(text, q.help, default, lambda value: q.check(value))
    if q.kind == "choice":
        return ui.ask_choice(text, q.help, q.options, default, q.details)
    if q.kind == "yes/no":
        return ui.ask_yes_no(text, q.help, "n" if default == "no" else "y")
    if q.kind == "layer":
        return ui.ask_layer(q.options, text, default, q.counts, q.help)
    if q.kind == "layers":
        return ui.ask_layers(q.options, text, default or "", q.counts, q.none_text)
    if q.kind == "materials":
        return ui.ask_materials(text, default)
    if q.kind == "colours":
        return ask_colours(values[q.materials_key], default)
    raise ValueError(f"Unknown kind of question: {q.kind}")


def answer_page(stack, questions, help_text=""):
    """The answers of a page: questions with no computation between them (example: step 4 before the 3D build).
    The terminal asks the questions with no good saved answer, one at a time (answer_all). A front end with forms
    (the window) shows all the questions of the page as one form, when an answer is missing or bad."""
    if not ui.shows_forms():
        return answer_all(stack, questions)
    values = {}
    for q in questions:
        if q.needed(values) and q.key in stack and q.check(stack[q.key], values) is None:
            values[q.key] = stack[q.key]
    if all(q.key in values for q in questions if q.needed(values)):
        return {q.key: values[q.key] for q in questions if q.needed(values)}
    result = ui.ask_page(help_text, questions, {q.key: stack[q.key] for q in questions if q.key in stack})
    for key, value in result.items():
        stack[key] = value
        answers.PREVIOUS.pop(key, None)
    answers.HISTORY.append((answers.CURRENT_STEP, list(result)[-1]))   # Back from the next question comes here
    if answers.SAVE:
        answers.SAVE(stack)
    return result


def answer_all(stack, questions):
    """The answers of the questions, as {key: answer}. A saved good answer stays; each necessary question with no
    good answer is asked, one at a time, and saved at once (answers.answer)."""
    values = {}
    for q in questions:
        if q.needed(values):
            values[q.key] = answer(stack, q.key, lambda q=q: ask(q, values),
                                   is_valid=lambda value, q=q: q.check(value, values) is None)
    return values
