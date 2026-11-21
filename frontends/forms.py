"""
The parts of the forms of the window (review finding CR-07): a form shows all the questions of a step (or of a part
of a step) together, in place of one question at a time.

  Field      one field: the widgets of one question (backend.questions.Question), its label, help and problem.
  PageForm   a simple form: the questions of a page, one under the other (example: step 4 before the 3D build).
The form of step 3 (one card for each layer) is in stack_form.py; it uses Field too.
The questions, their default answers and their checks come from the back end: these files only show them.
"""
import tkinter as tk
from tkinter import ttk

from backend.answers import join_colour, parse_materials, read_colour, shown
from backend.questions import colour_names
from frontends.theme import GREY_ON_WHITE, PERLE, RED, TAUPE, WHITE, mix


def style_combobox(app):
    """The look of the dropdown fields: flat, white, in the colours of the theme."""
    style = ttk.Style(app.root)
    style.configure("Form.TCombobox", fieldbackground=WHITE, background=WHITE, foreground=TAUPE, bordercolor=PERLE,
                    lightcolor=WHITE, darkcolor=WHITE, arrowcolor=GREY_ON_WHITE, padding=app.px(4))
    style.map("Form.TCombobox", fieldbackground=[("readonly", WHITE)], selectbackground=[("readonly", WHITE)],
              selectforeground=[("readonly", TAUPE)], bordercolor=[("focus", RED)])
    app.root.option_add("*TCombobox*Listbox.font", app.font["body"])


def swatch(form, parent, colour, text, size=12):
    """A small colour square and a text. Return the widgets."""
    px = form.px
    canvas = tk.Canvas(parent, width=px(size), height=px(size), bg=WHITE, highlightthickness=0)
    picked = read_colour(colour or "")
    canvas.create_rectangle(0, 0, px(size) - 1, px(size) - 1, outline="#7f7a77",
                            fill=mix(picked[0], WHITE, 1 - picked[1] / 100) if picked else WHITE)
    canvas.pack(side="left", padx=(0, px(6)))
    label = tk.Label(parent, text=text, font=form.font["body"], fg=TAUPE, bg=WHITE)
    label.pack(side="left", padx=(0, px(14)))
    return [canvas, label]


class PageForm:
    """The questions of one page as one form, one field under the other, each with its help text.
    values = the saved answers ({key: answer}); a question with no answer starts with its default answer."""

    def __init__(self, app, parent, help_text, questions, values):
        self.app, self.px, self.font = app, app.px, app.font
        self.questions = questions
        self.layers = [dict(values)]                     # one "layer": the answers of the page (Field uses it)
        self.colours = [{}]
        self.errors = {}
        self.fields = {}
        self.fill_defaults()
        px, font = self.px, self.font
        from frontends.window import ScrollArea, STEPS
        step = app.current_step
        self.frame = tk.Frame(parent, bg=WHITE, padx=px(24), pady=px(12))
        tk.Label(self.frame, text=f"Step {step}: {STEPS[step - 1][1]}", font=font["heading"], fg=RED, bg=WHITE,
                 anchor="w").pack(fill="x")
        if help_text:
            tk.Label(self.frame, text=help_text, font=font["body"], fg=GREY_ON_WHITE, bg=WHITE,
                     anchor="w").pack(fill="x")
        self.scroll = ScrollArea(self.frame, max_height=px(400), bg=WHITE)
        self.scroll.pack(fill="both", expand=True, pady=(px(10), 0))
        self.frame.bind("<Configure>", self.fit)
        style_combobox(app)
        self.build()

    def needed(self):
        values = self.layers[0]
        return [q for q in self.questions if q.needed(values)]

    def fill_defaults(self):
        values = self.layers[0]
        for q in self.questions:
            if q.needed(values) and q.key not in values:
                default = q.initial(values)
                if q.kind in ("choice", "layer"):
                    options = list(q.options)
                    default = default if default in options else options[0]
                elif q.kind == "yes/no":
                    default = default or "yes"
                values[q.key] = "" if default is None else str(default)

    def fit(self, event):
        used = sum(w.winfo_reqheight() for w in self.frame.winfo_children() if w is not self.scroll)
        self.scroll.max_height = max(self.px(120), event.height - used - self.px(40))
        self.scroll.fit()

    def build(self):
        for widget in self.scroll.inner.winfo_children():
            widget.destroy()
        self.fields = {}
        for q in self.needed():
            cell = tk.Frame(self.scroll.inner, bg=WHITE)
            cell.pack(fill="x", pady=(0, self.px(14)))
            self.fields[q.key] = Field(self, cell, q, 0, q.key, inline_help=True)
        self.scroll.fit()

    def set_value(self, name, value, rebuild=False):
        before = [q.key for q in self.needed()]
        self.layers[0][name] = value
        self.errors.pop((0, name), None)
        self.fill_defaults()
        if rebuild or [q.key for q in self.needed()] != before:      # another question is necessary now
            self.build()

    def show_help(self, text, field=None):
        if field is not None and field.help_label is not None and field.help_label.winfo_exists():
            field.help_label.configure(text=text or "")

    def swatch(self, parent, colour, text, size=12):
        return swatch(self, parent, colour, text, size)

    def get(self):
        """Check all the values. Return the answers of the necessary questions, or an Error."""
        from frontends.window import Error
        values = self.layers[0]
        self.errors = {}
        for q in self.needed():
            problem = q.check(values.get(q.key), values)
            if problem:
                self.errors[(0, q.key)] = problem
        if self.errors:
            self.build()
            return Error("Check the values in red.")
        return {q.key: values[q.key] for q in self.needed()}


class Field:
    """One field of a form: a label, the widgets of one question and, after Next, its problem in red.
    form = the form (StackForm or PageForm): it keeps the answers in form.layers[index][name].
    inline_help = True: the help text shows under the field (else the form shows it, at a click)."""

    def __init__(self, form, cell, question, index, name, inline_help=False):
        self.form, self.q, self.index, self.name = form, question, index, name
        px, font = form.px, form.font
        value = form.layers[index].get(name, "")
        tk.Label(cell, text=question.label or question.title({}), font=font["small"], fg=GREY_ON_WHITE, bg=WHITE,
                 anchor="w").pack(fill="x")
        kind = question.kind
        if kind in ("text", "materials", "number"):
            if kind == "materials" and parse_materials(value):         # show µm, as in the cards
                value = ", ".join(f"{m} {shown(t)}" for m, t in parse_materials(value))
            self.variable = tk.StringVar(value=value)
            self.widget = tk.Entry(cell, textvariable=self.variable, font=font["body"], relief="solid", bd=1, fg=TAUPE,
                                   highlightthickness=1, highlightcolor=RED, highlightbackground=PERLE)
            self.widget.pack(fill="x", ipady=px(4))
            self.variable.trace_add("write", lambda *_: form.set_value(name, self.variable.get().strip()))
        elif kind in ("choice", "layer"):
            options = question.options if isinstance(question.options, dict) else {v: v for v in question.options}
            self.values = list(options)
            self.widget = ttk.Combobox(cell, state="readonly", values=[options[v] for v in self.values],
                                       font=font["body"], style="Form.TCombobox")
            self.widget.current(self.values.index(value) if value in self.values else 0)
            self.widget.pack(fill="x")
            self.widget.bind("<<ComboboxSelected>>", lambda e: self.chosen())
        elif kind == "yes/no":
            self.marks = {}
            line = tk.Frame(cell, bg=WHITE)
            line.pack(fill="x", pady=(px(4), 0))
            for option in ("yes", "no"):
                mark = tk.Canvas(line, width=px(18), height=px(18), bg=WHITE, highlightthickness=0, cursor="hand2")
                mark.pack(side="left")
                text = tk.Label(line, text=option, font=font["body"], fg=TAUPE, bg=WHITE, cursor="hand2")
                text.pack(side="left", padx=(px(6), px(22)))
                for widget in (mark, text):
                    widget.bind("<Button-1>", lambda e, o=option: self.pick(o))
                self.marks[option] = mark
            self.paint_marks(value)
        elif kind == "layers":
            self.ticked = [] if not value else (["none"] if value == "none" else
                                                [v.strip() for v in value.split(",") if v.strip()])
            self.boxes = {}
            line = tk.Frame(cell, bg=WHITE)
            line.pack(fill="x", pady=(px(4), 0))
            choices = ([("none", question.none_text)] if question.none_text else []) + [(n, n) for n in question.options]
            for number, (option, text) in enumerate(choices):
                holder = tk.Frame(line, bg=WHITE)
                holder.grid(row=number // 3, column=number % 3, sticky="w", padx=(0, px(18)), pady=px(2))
                box = tk.Canvas(holder, width=px(18), height=px(18), bg=WHITE, highlightthickness=0, cursor="hand2")
                box.pack(side="left")
                label = tk.Label(holder, text=text, font=font["body"], fg=TAUPE, bg=WHITE, cursor="hand2")
                label.pack(side="left", padx=(px(6), 0))
                for widget in (box, label):
                    widget.bind("<Button-1>", lambda e, o=option: self.toggle(o))
                self.boxes[option] = box
            self.paint_boxes()
        elif kind == "colours":
            self.line = tk.Frame(cell, bg=WHITE)
            self.line.pack(fill="x", pady=(px(4), 0))
            self.refresh()
        self.help_label = None
        if inline_help:
            self.help_label = tk.Label(cell, text=self.help(), font=font["small"], fg=GREY_ON_WHITE, bg=WHITE,
                                       anchor="w", justify="left", wraplength=px(520))
            self.help_label.pack(fill="x", pady=(px(2), 0))
        problem = form.errors.get((index, name))
        if problem:
            tk.Label(cell, text=problem, font=font["small"], fg=RED, bg=WHITE, anchor="w", justify="left",
                     wraplength=px(300)).pack(fill="x")
        for widget in cell.winfo_children():
            widget.bind("<FocusIn>", lambda e: form.show_help(self.help(), self), add="+")
            widget.bind("<Button-1>", lambda e: form.show_help(self.help(), self), add="+")

    def help(self):
        if self.q.kind == "choice" and self.q.details:
            return self.q.details.get(self.form.layers[self.index].get(self.name), self.q.help)
        return self.q.help

    def chosen(self):
        value = self.values[self.widget.current()]
        self.form.set_value(self.name, value, rebuild=self.name == "type")
        self.form.show_help(self.help(), self)

    def pick(self, option):
        self.paint_marks(option)
        self.form.set_value(self.name, option)

    def paint_marks(self, value):
        px = self.form.px
        for option, mark in self.marks.items():
            on = option == value
            mark.delete("all")
            mark.create_oval(px(2), px(2), px(16), px(16), outline=RED if on else GREY_ON_WHITE, fill=WHITE, width=px(1.5))
            if on:
                mark.create_oval(px(6), px(6), px(12), px(12), outline=RED, fill=RED)

    def toggle(self, option):
        """A tick. "none" (example: "no openings") and the mask layers exclude each other."""
        if option in self.ticked:
            self.ticked.remove(option)
        elif option == "none":
            self.ticked = ["none"]
        else:
            self.ticked = [o for o in self.ticked if o != "none"] + [option]
        order = list(self.boxes)
        self.ticked.sort(key=order.index)
        self.paint_boxes()
        self.form.set_value(self.name, "none" if self.ticked == ["none"] else ", ".join(self.ticked))

    def paint_boxes(self):
        px = self.form.px
        for option, box in self.boxes.items():
            on = option in self.ticked
            box.delete("all")
            box.create_rectangle(px(2), px(2), px(16), px(16), outline=RED if on else GREY_ON_WHITE,
                                 fill=RED if on else WHITE, width=px(1.5))
            if on:
                box.create_line(px(5), px(9), px(8), px(12), px(13), px(5), fill=WHITE, width=px(2))

    def refresh(self):
        """Colours: one button for each different material of the materials field."""
        for widget in self.line.winfo_children():
            widget.destroy()
        materials = colour_names(self.form.layers[self.index].get("materials", ""))
        if not materials:
            tk.Label(self.line, text="Write the materials first.", font=self.form.font["body"], fg=GREY_ON_WHITE,
                     bg=WHITE).pack(side="left")
        for material in materials:
            colour = self.form.colours[self.index].get(material)
            holder = tk.Frame(self.line, bg=WHITE, cursor="hand2", highlightthickness=1, highlightbackground=PERLE,
                              padx=self.form.px(8), pady=self.form.px(5))
            holder.pack(side="top", anchor="w", pady=(0, self.form.px(4)))
            parts = [holder] + self.form.swatch(holder, colour, f"{material}  {colour or 'select colour'}", size=14)
            parts[-1].pack_configure(padx=0)
            for widget in parts:
                widget.bind("<Button-1>", lambda e, m=material: self.pick_colour(m))

    def pick_colour(self, material):
        from frontends.colour_window import ColourWindow
        start = read_colour(self.form.colours[self.index].get(material, "")) or ("#808080", 0)
        picked = ColourWindow(start[0], start[1], master=self.form.app.root).run()
        if picked:
            self.form.colours[self.index][material] = join_colour(*picked)
            self.form.errors.pop((self.index, "colours"), None)
            self.refresh()
            self.form.draw()
