"""
Step 3 in the window: the stack as one form.

One card for each layer, top layer first. A closed card shows all the values of its layer in two lines; a click
opens it. The open card has one field for each necessary question. The questions, their default answers and their
checks come from the back end (backend.questions.Question): this file only shows them.
The stack drawing on the right changes at once and marks the open layer. Next checks all the values.
"""
import tkinter as tk

from backend.answers import parse_materials, read_colour, shown
from backend.questions import colour_names
from frontends.forms import Field, style_combobox, swatch
from frontends.theme import CANARD, GREY_ON_WHITE, PERLE, RED, TAUPE, WHITE, mix


def short(key):
    """"layer 3 materials" -> "materials"."""
    return key.split(" ", 2)[2]


def draw_stack(canvas, layers, font, px, width, marked=None):
    """Draw the stack on a canvas, top to bottom: one bar in the colour of each material (mixed with white if
    transparent), the material, and for the first material of each layer: its name, its type and its openings.
    marked = the index of a layer (from the bottom): a red bar on its left. Return the height of the drawing."""
    rows = []
    for index in range(len(layers) - 1, -1, -1):
        layer = layers[index]
        materials = list(reversed(layer["materials"])) or [dict(name="no materials yet", thickness="", colour=PERLE)]
        for i, m in enumerate(materials):
            thickness = m["thickness"].replace("um", "µm")
            text = f"{m['name']} {thickness}".strip() + (
                f"   {m['transparency']}% transparent" if m.get("transparency") else "")
            about = ""
            if i == 0:
                about = layer["type"]
                if layer["type"] == "encapsulation":
                    openings = layer.get("openings") or "none"
                    about += " · " + ("no openings" if openings == "none" else f"openings: {openings}")
                    about += f" · cleave: {layer.get('cleave', '')}"
            rows.append((index, layer, m, text, layer["name"] if i == 0 else "", about))
    left = px(18) if marked is not None else 0
    bar_width, bar_height, gap = px(140), px(20), px(4)
    x_material = left + bar_width + px(16)
    x_name = x_material + max((font["body"].measure(r[3]) for r in rows), default=0) + px(22)
    y = px(4)
    mark = []                                             # top and bottom of the marked layer
    for index, layer, m, text, name, about in rows:
        w = bar_width * (0.65 if layer["type"] == "electrode coating" else 1)
        x0 = left + (bar_width - w) / 2
        canvas.create_rectangle(x0, y, x0 + w, y + bar_height, outline=PERLE,
                                fill=mix(m["colour"], WHITE, 1 - m.get("transparency", 0) / 100))
        canvas.create_text(x_material, y + bar_height / 2, text=text, anchor="w", font=font["body"], fill=TAUPE)
        bottom = y + bar_height
        if name:
            canvas.create_text(x_name, y + bar_height / 2, text=name, anchor="w", font=font["bold"], fill=TAUPE)
            item = canvas.create_text(x_name, y + bar_height, text=about, anchor="nw", font=font["small"],
                                      fill=GREY_ON_WHITE, width=max(width - x_name - px(4), px(80)))
            bottom = max(bottom, canvas.bbox(item)[3])
        if index == marked:
            mark += [y, bottom]
        y = bottom + gap
    if mark:
        canvas.create_rectangle(px(6), min(mark) - gap / 2, px(10), max(mark) + gap / 2, fill=RED, width=0)
    return y + px(2)


class StackForm:
    """The form of step 3. layers = the answers of the layers from the bottom up ([{question: answer}]).
    make_questions(number, layers below) and problems(layers) come from the back end (ui.edit_stack)."""

    def __init__(self, app, parent, layers, make_questions, problems, open_layer=None):
        self.app, self.px, self.font = app, app.px, app.font
        self.make_questions, self.problems = make_questions, problems
        self.layers = [{k: v for k, v in values.items() if k != "has a layer on top"} for values in layers]
        self.colours = [self.colour_map(values) for values in self.layers]   # {material: colour} of each layer
        if not self.layers:
            self.add_layer(build=False)
        for index in range(len(self.layers)):
            self.fill_defaults(index)
        self.open_index = open_layer if open_layer is not None and open_layer < len(self.layers) else             len(self.layers) - 1
        self.errors = {}                                  # (layer index, question) -> the problem
        self.focus_help = ""
        self.fields = {}                                  # the fields of the open card: question -> Field

        px, font = self.px, self.font
        self.frame = tk.Frame(parent, bg=WHITE, padx=px(24), pady=px(12))
        tk.Label(self.frame, text="Step 3: build stack", font=font["heading"], fg=RED, bg=WHITE,
                 anchor="w").pack(fill="x")
        tk.Label(self.frame, text="One line for each layer, top layer first. Click a line to change its values.",
                 font=font["body"], fg=GREY_ON_WHITE, bg=WHITE, anchor="w").pack(fill="x")
        add = tk.Label(self.frame, text="+  Add a layer on top", font=font["bold"], fg=CANARD, bg=WHITE,
                       cursor="hand2", anchor="w")
        add.pack(fill="x", pady=(px(8), px(6)))
        add.bind("<Button-1>", lambda e: self.add_layer())
        from frontends.window import ScrollArea
        self.scroll = ScrollArea(self.frame, max_height=px(400), bg=WHITE)
        self.scroll.pack(fill="both", expand=True)
        self.frame.bind("<Configure>", self.fit)
        style_combobox(app)
        self.build()

    # ── the answers ──

    def colour_map(self, values):
        names = [m for m, _ in parse_materials(values.get("materials", "")) or []]
        colours = [c.strip() for c in values.get("colours", "").split(",")]
        return {name: colour for name, colour in zip(names, colours) if colour}

    def full(self, index):
        """The answers of a layer with the full keys of the back end ("layer 3 name"), colours as one text."""
        values = dict(self.layers[index])
        materials = parse_materials(values.get("materials", "")) or []
        colours = self.colours[index]
        values["colours"] = ", ".join(colours.get(name, "") for name, _ in materials) if all(
            name in colours for name, _ in materials) and materials else ""
        return {f"layer {index + 1} {k}": v for k, v in values.items()}

    def questions(self, index):
        return self.make_questions(index + 1, [dict(v) for v in self.layers[:index]])

    def fill_defaults(self, index):
        """Give each necessary question of a layer with no answer its default answer."""
        values, full = self.layers[index], self.full(index)
        for q in self.questions(index):
            name = short(q.key)
            if not q.needed(full) or name in values:
                continue
            if q.kind == "colours":
                for material in colour_names(values.get("materials", "")):
                    if material not in self.colours[index] and (q.default or {}).get(material):
                        self.colours[index][material] = q.default[material]
                continue
            if q.kind in ("choice", "layer"):
                options = list(q.options)
                values[name] = q.default if q.default in options else options[0]
            elif q.kind == "yes/no":
                values[name] = q.default or "yes"
            else:
                values[name] = q.default or ""
            full = self.full(index)

    def answers(self):
        """The answers of all the layers (only the necessary questions), from the bottom up."""
        result = []
        for index in range(len(self.layers)):
            full = self.full(index)
            result.append({short(q.key): full.get(q.key, "") for q in self.questions(index) if q.needed(full)})
        return result

    def get(self):
        """Check all the values. Return the answers, or an Error (the window shows it; Next does nothing)."""
        from frontends.window import Error
        self.errors = {}
        for index in range(len(self.layers)):
            full = self.full(index)
            for q in self.questions(index):
                problem = q.needed(full) and q.check(full.get(q.key), full)
                if problem:
                    self.errors[(index, short(q.key))] = problem
        if self.errors:
            self.open_index = max(index for index, _ in self.errors)       # the highest card with a problem
            self.build()
            return Error("Check the values in red.")
        problems = self.problems(self.answers())
        if problems:
            return Error("  ".join(problems))
        return self.answers()

    # ── the changes ──

    def add_layer(self, build=True):
        self.layers.append({})
        self.colours.append({})
        self.fill_defaults(len(self.layers) - 1)
        self.open_index = len(self.layers) - 1
        if build:
            self.build()
            self.scroll.canvas.yview_moveto(0)

    def remove_layer(self, index):
        del self.layers[index], self.colours[index]
        self.errors = {}
        self.open_index = min(index, len(self.layers) - 1)
        self.build()

    def open(self, index):
        if index != self.open_index:
            self.open_index = index
            self.build()

    def set_value(self, name, value, rebuild=False):
        """A field changed. A new type changes the necessary questions: then the card is built again."""
        index = self.open_index
        self.layers[index][name] = value
        self.errors.pop((index, name), None)
        if name == "materials":
            self.fill_defaults(index)
            if "colours" in self.fields:
                self.fields["colours"].refresh()
        if rebuild:
            self.fill_defaults(index)
            self.build()
        else:
            self.header_name.configure(text=self.layers[index].get("name") or "New layer")
            self.draw()

    # ── the widgets ──

    def fit(self, event):
        """The list of cards takes all the height of the form."""
        used = sum(w.winfo_reqheight() for w in self.frame.winfo_children() if w is not self.scroll)
        self.scroll.max_height = max(self.px(120), event.height - used - self.px(36))
        self.scroll.fit()

    def build(self):
        """Make all the cards again (after a change of the open card, a new layer or a removed layer)."""
        for widget in self.scroll.inner.winfo_children():
            widget.destroy()
        self.fields = {}
        for index in range(len(self.layers) - 1, -1, -1):
            if index == self.open_index:
                self.open_card(index)
            else:
                self.closed_card(index)
        self.scroll.fit()
        self.draw()
        self.app.root.after_idle(lambda: self.open_frame.winfo_exists() and self.scroll.show(self.open_frame))

    def closed_card(self, index):
        px, font = self.px, self.font
        values = self.layers[index]
        problem = any(i == index for i, _ in self.errors)
        card = tk.Frame(self.scroll.inner, bg=WHITE, padx=px(14), pady=px(8), cursor="hand2", highlightthickness=1,
                        highlightbackground=RED if problem else PERLE)
        card.pack(fill="x", pady=(0, px(8)))
        top = tk.Frame(card, bg=WHITE)
        top.pack(fill="x")
        parts = [card, top]
        for text, style, colour in ((str(index + 1), "bold", GREY_ON_WHITE),
                                    (values.get("name") or "New layer", "bold", TAUPE),
                                    (f"{values.get('type', '')}  ·  {values.get('shape', '')}", "body", GREY_ON_WHITE)):
            label = tk.Label(top, text=text, font=font[style], fg=colour, bg=WHITE)
            label.pack(side="left", padx=(0, px(10)))
            parts.append(label)
        line = tk.Frame(card, bg=WHITE)
        line.pack(fill="x", pady=(px(4), 0))
        parts.append(line)
        tk.Frame(line, bg=WHITE, width=px(14)).pack(side="left")
        for name, thickness in parse_materials(values.get("materials", "")) or []:
            parts += self.swatch(line, self.colours[index].get(name), f"{name} {shown(thickness)}")
        if values.get("type") == "encapsulation":
            openings = values.get("openings") or "none"
            extra = ("no openings" if openings == "none" else f"openings: {openings}") + \
                f"  ·  cleave: {values.get('cleave', '')}"
        else:
            extra = f"surface: {values.get('surface', '')}"
        text = "Check this layer." if problem else extra
        long = len(text) > 32                                 # a long text (many openings) gets its own line
        label = tk.Label(card if long else line, text=text, font=font["body"], fg=RED if problem else GREY_ON_WHITE,
                         bg=WHITE, anchor="w", justify="left", wraplength=px(520))
        label.pack(fill="x", padx=(px(24), 0), pady=(px(2), 0)) if long else label.pack(side="right")
        parts.append(label)
        for widget in parts:
            widget.bind("<Button-1>", lambda e, i=index: self.open(i))

    def swatch(self, parent, colour, text, size=12):
        return swatch(self, parent, colour, text, size)

    def open_card(self, index):
        px, font = self.px, self.font
        card = self.open_frame = tk.Frame(self.scroll.inner, bg=WHITE, highlightthickness=1, highlightbackground=PERLE)
        card.pack(fill="x", pady=(0, px(8)))
        tk.Frame(card, bg=RED, width=px(4)).pack(side="left", fill="y")
        body = tk.Frame(card, bg=WHITE, padx=px(14), pady=px(10))
        body.pack(side="left", fill="both", expand=True)
        top = tk.Frame(body, bg=WHITE)
        top.pack(fill="x")
        tk.Label(top, text=str(index + 1), font=font["bold"], fg=GREY_ON_WHITE, bg=WHITE).pack(side="left")
        self.header_name = tk.Label(top, text=self.layers[index].get("name") or "New layer", font=font["bold"],
                                    fg=TAUPE, bg=WHITE)
        self.header_name.pack(side="left", padx=(px(10), 0))
        if len(self.layers) > 1:
            remove = tk.Label(top, text="Remove layer", font=font["small"], fg=GREY_ON_WHITE, bg=WHITE, cursor="hand2")
            remove.pack(side="right")
            remove.bind("<Button-1>", lambda e: self.remove_layer(index))

        grid = tk.Frame(body, bg=WHITE)
        grid.pack(fill="x", pady=(px(6), 0))
        grid.grid_columnconfigure(0, weight=1, uniform="column")
        grid.grid_columnconfigure(1, weight=1, uniform="column")
        full = self.full(index)
        row = column = 0
        needed = [q for q in self.questions(index) if q.needed(full)]
        for q in sorted(needed, key=lambda q: q.kind == "layers"):          # the ticks take a full row: last
            wide = q.kind == "layers"
            if wide and column == 1:
                row, column = row + 1, 0
            cell = tk.Frame(grid, bg=WHITE)
            cell.grid(row=row, column=column, columnspan=2 if wide else 1, sticky="new",
                      padx=(0, px(16) if column == 0 and not wide else 0), pady=(0, px(8)))
            self.fields[short(q.key)] = Field(self, cell, q, index, short(q.key))
            if wide or column == 1:
                row, column = row + 1, 0
            else:
                column = 1
        self.help_label = tk.Label(body, text=self.focus_help, font=font["small"], fg=GREY_ON_WHITE, bg=WHITE,
                                   anchor="w", justify="left")
        self.help_label.pack(fill="x")
        if not self.layers[index].get("name") and "name" in self.fields:    # a new layer: type its name at once
            self.fields["name"].widget.focus_set()

    def show_help(self, text, field=None):
        self.focus_help = text or ""
        if self.help_label.winfo_exists():
            self.help_label.configure(text=self.focus_help)

    def draw(self):
        """The stack drawing on the right, with a red mark on the open layer."""
        layers = []
        for index, values in enumerate(self.layers):
            materials = []
            for name, thickness in parse_materials(values.get("materials", "")) or []:
                picked = read_colour(self.colours[index].get(name, "")) or (PERLE, 0)
                materials.append(dict(name=name, thickness=thickness, colour=picked[0], transparency=picked[1]))
            layers.append(dict(name=values.get("name") or "New layer", type=values.get("type", ""),
                               materials=materials, openings=values.get("openings"), cleave=values.get("cleave")))
        self.app.show_drawing("Your stack", lambda canvas, width: draw_stack(
            canvas, layers, self.font, self.px, width, marked=self.open_index))
