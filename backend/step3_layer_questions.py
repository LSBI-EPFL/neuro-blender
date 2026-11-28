"""
Step 3: build the stack of the device, layer by layer, from the bottom up.

Describe the layers in the order of your run card. A layer = one DXF shape and one type.
A layer can have more than one material: list each material with its thickness, from the bottom up.
Example: the tracks = one layer with 3 materials: "Ti 25 nm, Pt 150 nm, Ti 25 nm".

Each layer has one type:
  - encapsulation:     a polymer layer (PI, PDMS, parylene). It can have openings, and it can be cleaved.
                       In the exploded view, a cleaved layer bends away from the tracks:
                       below the tracks it bends down, above the tracks it bends up.
  - tracks:            the metal lines from the electrodes to the pads. They stay flat.
  - electrode coating: material on the electrodes only. It floats above the electrodes.

The shape of each layer comes from one mask layer. Many layers can use the same mask layer.
After each layer, the script shows the stack so far. At the end, it saves an image of the stack: 4_stack.png.
"""
import os

import matplotlib
matplotlib.use("Agg")                      # write image files only, open no window
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle

from backend import answers, ui
from backend.answers import answer, join_colour, parse_materials, split_colour
from backend.questions import Question, answer_all

TYPES = {
    "encapsulation": "Polymer layer (PI, PDMS, parylene). Openings and cleave possible.",
    "tracks": "Metal lines from electrodes to pads. Stay flat in image.",
    "electrode coating": "Material on electrodes only. Floats above electrodes in image.",
}
SURFACES = {"shiny": "Shines like metal.", "matte": "No shine."}
REMEMBERED = {}            # {material: colour}: the last colours of all designs (run() reads them from the file)


def layer_questions(number, below, layer_names, counts, outline_layer, earlier_colours, above_tracks=False,
                    old=None):
    """The questions about one layer (Question objects), in their order. below = the layer under it (a dictionary),
    or None. counts = {mask layer: number of shapes}. earlier_colours = {material: colour} of the layers below.
    above_tracks = True when a tracks layer is below this layer. old = {key: old answer} (after going back or a
    change): the old answers are the default answers."""
    key = f"layer {number}"
    old = old if old is not None else answers.PREVIOUS
    before = lambda question, fallback=None: old.get(f"{key} {question}", fallback)
    encapsulation = lambda values: values.get(f"{key} type") == "encapsulation"
    # Colours: the old colour of a material of this layer, else the colour of the material in a layer below, else
    # the last colour of the material in any design (REMEMBERED).
    old_names = [m for m, _ in parse_materials(before("materials", "")) or []]
    old_colours = dict(zip(old_names, [c.strip() for c in before("colours", "").split(",")]))
    colours = {**REMEMBERED, **earlier_colours, **{name: colour for name, colour in old_colours.items() if colour}}
    return [
        Question(f"{key} name", "text", "Name?", "shows on image", default=before("name"), label="Name"),
        Question(f"{key} type", "choice", "Type?", options={t: t for t in TYPES}, details=TYPES,
                 default=before("type", below["type"] if below else None), label="Type"),
        Question(f"{key} shape", "layer", "Which mask layer draws this layer?", options=layer_names, counts=counts,
                 default=before("shape", below["shape"] if below else outline_layer), label="Mask layer"),
        Question(f"{key} materials", "materials", "Materials?", "bottom up, with commas. Example: Ti 25 nm, Pt 150 nm",
                 default=before("materials"), label="Materials and thicknesses"),
        Question(f"{key} colours", "colours", "Colours?", "click a colour to change it",
                 default=colours, materials_key=f"{key} materials", label="Colours"),
        # One list: "no openings" or the mask layers of the openings. An answer with no tick is refused, so an
        # empty answer is never saved as "no openings" in silence. Below the tracks, "no openings" is the default.
        Question(f"{key} openings", "layers",
                 lambda values: f"Which mask layers draw the openings in {values.get(f'{key} name')}?",
                 "mask layers that open this layer", options=layer_names, counts=counts, none_text="no openings",
                 default=before("openings", "" if above_tracks else "none"), needed=encapsulation, label="Openings"),
        Question(f"{key} cleave", "yes/no", "Cleave this layer?",
                 "Cleaved layer bends away from tracks in image, so tracks show.",
                 default="no" if before("cleave") == "no" else "yes", needed=encapsulation, label="Cleave"),
        Question(f"{key} surface", "choice", "Surface?", options={s: s for s in SURFACES}, details=SURFACES,
                 default=before("surface", below["surface"] if below and "surface" in below else "shiny"),
                 needed=lambda values: not encapsulation(values), label="Surface"),
    ]


def make_layer(number, values):
    """The layer (a dictionary) from the answers of its questions (values = {key: answer})."""
    key = f"layer {number}"
    pairs = parse_materials(values[f"{key} materials"])
    colours = values[f"{key} colours"].split(",")
    layer = dict(number=number, name=values[f"{key} name"], type=values[f"{key} type"], shape=values[f"{key} shape"],
                 materials=[dict(name=m, thickness=t, colour=split_colour(c)[0], transparency=split_colour(c)[1])
                            for (m, t), c in zip(pairs, colours)])
    if layer["type"] == "encapsulation":
        layer["openings"], layer["cleave"] = values[f"{key} openings"], values[f"{key} cleave"]
    else:
        layer["surface"] = values[f"{key} surface"]
    return layer


def layers_in(answers_now):
    """The answers of the layers in a dictionary of answers, from the bottom up: [{question: answer}], with the
    short names of the questions ("name", "materials", "has a layer on top", ...)."""
    layers = []
    while any(k.startswith(f"layer {len(layers) + 1} ") for k in answers_now):
        start = f"layer {len(layers) + 1} "
        layers.append({k[len(start):]: v for k, v in answers_now.items() if k.startswith(start)})
    return layers


def form_questions(number, below, layer_names, counts, outline_layer):
    """The questions of layer number for the form. below = the answers of the layers under it ([{question:
    answer}]); they give the default answers of a new layer (type, mask layer, surface, colours)."""
    previous = None
    if below:
        previous = {k: below[-1][k] for k in ("type", "shape", "surface") if below[-1].get(k)}
        previous.setdefault("type", None)
        previous.setdefault("shape", outline_layer)
    earlier = {}
    for values in below:
        names = [m for m, _ in parse_materials(values.get("materials", "")) or []]
        for name, colour in zip(names, values.get("colours", "").split(",")):
            if colour.strip():
                earlier.setdefault(name, colour.strip())
    above_tracks = any(values.get("type") == "tracks" for values in below)
    return layer_questions(number, previous, layer_names, counts, outline_layer, earlier, above_tracks, old={})


def complete(layers, layer_names, counts, outline_layer):
    """True if the answers of the layers are all there and good, the stack ends, and it keeps the stack rules."""
    if not layers:
        return False
    for number, values in enumerate(layers, start=1):
        full = {f"layer {number} {k}": v for k, v in values.items()}
        for q in form_questions(number, layers[:number - 1], layer_names, counts, outline_layer):
            if q.needed(full) and q.check(full.get(q.key), full):
                return False
        if values.get("has a layer on top") != ("yes" if number < len(layers) else "no"):
            return False
    return not check_stack([{"type": values["type"]} for values in layers])


def edit_in_form(stack, layer_names, counts, outline_layer):
    """Step 3 as one form (the window). Return the layers. The form opens only when an answer is missing or bad
    (a new stack, going back to step 3, or a changed layer); the old answers are in the form."""
    saved = layers_in(stack)
    removed = {k: v for k, v in answers.PREVIOUS.items() if k.startswith("layer ")}
    if not removed and complete(saved, layer_names, counts, outline_layer):
        return [make_layer(n, {f"layer {n} {k}": v for k, v in values.items()}) for n, values in enumerate(saved, 1)]
    changed = sorted({int(k.split()[1]) for k in removed if not k.endswith("has a layer on top")})
    if len(changed) == len(layers_in(removed)) > 1:       # the whole step (go to step 3): open the top layer
        changed = []
    layers = ui.edit_stack(
        layers_in({**removed, **{k: v for k, v in stack.items() if k.startswith("layer ")}}),
        lambda number, below: form_questions(number, below, layer_names, counts, outline_layer),
        lambda values: check_stack([{"type": v.get("type")} for v in values]),
        open_layer=changed[0] - 1 if changed else None)
    for key in [k for k in stack if k.startswith("layer ")] + list(removed):
        stack.pop(key, None)
        answers.PREVIOUS.pop(key, None)
    for number, values in enumerate(layers, start=1):
        values["materials"] = ", ".join(f"{m} {t}" for m, t in parse_materials(values["materials"]))  # standard form
        stack.update({f"layer {number} {k}": v for k, v in values.items()})
        stack[f"layer {number} has a layer on top"] = "yes" if number < len(layers) else "no"
    answers.HISTORY.append((answers.CURRENT_STEP, f"layer {len(layers)} has a layer on top"))   # Back comes here
    if answers.SAVE:
        answers.SAVE(stack)
    return [make_layer(n, {f"layer {n} {k}": v for k, v in values.items()}) for n, values in enumerate(layers, 1)]


def ask_layer_description(stack, number, below, layer_names, counts, outline_layer, earlier_colours,
                          above_tracks=False):
    """Ask the questions about one layer that have no good saved answer, one at a time. Return the layer."""
    questions = layer_questions(number, below, layer_names, counts, outline_layer, earlier_colours, above_tracks)
    if any(q.key not in stack for q in questions[:5]):    # a title only when this layer has questions to ask
        ui.section(f"Layer {number}" + (" (bottom layer)" if number == 1 else ""))
    return make_layer(number, answer_all(stack, questions))


def check_stack(layers):
    """Return a list of problems in the stack (texts). An empty list = no problem."""
    problems = []
    kinds = [layer["type"] for layer in layers]
    if "tracks" not in kinds:
        problems.append("No tracks layer. Cleave needs tracks as centre.")
    else:
        last_track = max(i for i, k in enumerate(kinds) if k == "tracks")
        first_track = min(i for i, k in enumerate(kinds) if k == "tracks")
        if any(k != "tracks" for k in kinds[first_track:last_track + 1]):
            problems.append("Tracks layers must be one after the other.")
        if any(k == "electrode coating" for k in kinds[:last_track]):
            problems.append("Electrode coating below tracks. Put coatings above tracks.")
    return problems


def save_stack_image(layers, file):
    """Save a simple image of the stack. Each material is one bar. The bar heights are NOT to scale."""
    bars = [(layer, m) for layer in layers for m in layer["materials"]]
    fig, ax = plt.subplots(figsize=(6.5, 0.45 * len(bars) + 1))
    for row, (layer, m) in enumerate(bars):
        width = 0.6 if layer["type"] == "electrode coating" else 1.0   # coatings are on the electrodes only
        ax.add_patch(Rectangle(((1 - width) / 2, row), width, 0.9, facecolor=m["colour"], edgecolor="0.3", linewidth=0.5,
                               alpha=1 - m.get("transparency", 0) / 100))
        ax.text(1.08, row + 0.45, f"{m['name']}   {m['thickness']}   (layer {layer['number']}: {layer['name']}, {layer['type']})",
                va="center", fontsize=9)
    ax.set_xlim(0, 2.6)
    ax.set_ylim(-0.2, len(bars) + 0.1)
    ax.axis("off")
    ax.set_title("Your stack, bottom to top (heights not to scale)", fontsize=10)
    fig.savefig(file, dpi=150, bbox_inches="tight")
    plt.close(fig)


def run(device_layers, stack, project_folder):
    """Do step 3. Return the list of layers, from the bottom to the top."""
    ui.header(3)
    ui.note("Describe device layer by layer, bottom up, in run card order.\n"
            "Layer = one mask shape + one type. More materials possible: Ti 25 nm, Pt 150 nm, Ti 25 nm.\n"
            "Folder 3_device_layers: one image per mask layer of device.")
    names = list(device_layers)
    counts = {name: len(shapes["closed"]) for name, shapes in device_layers.items()}
    outline = stack.get("outline layer")
    projects_folder = os.path.dirname(project_folder)     # the colours file is the same for all designs
    REMEMBERED.clear()
    REMEMBERED.update(answers.remembered_colours(projects_folder))

    if ui.shows_forms():                                  # the window: all the layers in one form
        layers = edit_in_form(stack, names, counts, outline)
        answers.remember_colours(projects_folder, layers)
        ui.stack_drawing(layers)
        save_stack_image(layers, os.path.join(project_folder, "4_stack.png"))
        ui.show_path("Stack image:", os.path.join(project_folder, "4_stack.png"))
        return layers

    layers = []
    number = 1
    shown_once = False
    while True:
        below = layers[-1] if layers else None
        earlier_colours = {m["name"]: join_colour(m["colour"], m["transparency"]) for layer in layers
                           for m in layer["materials"]}
        answers_before = len(answers.HISTORY)
        above_tracks = any(layer["type"] == "tracks" for layer in layers)
        layers.append(ask_layer_description(stack, number, below, names, counts, outline, earlier_colours,
                                            above_tracks))
        if len(answers.HISTORY) > answers_before:          # show the stack only after new answers (less to read)
            ui.stack_drawing(layers)
            shown_once = True
        key = f"layer {number} has a layer on top"
        more = answer(stack, key, lambda: ui.ask_yes_no(
            "Add a layer on top?", default="n" if answers.PREVIOUS.get(key) == "no" else "y"),
            is_valid=lambda v: v in ("yes", "no"))
        if more == "no":
            problems = check_stack(layers)
            if not problems:
                break
            # A stack that breaks a rule is refused here, at the answer (not later in step 4): add a layer, or go
            # back to change a layer. "Add a layer on top?" comes again.
            for problem in problems:
                ui.warn(problem)
            ui.note("Add a layer on top, or go back (Esc or Back) to change a layer.")
            answers.forget(stack, key)
            layers.pop()
            continue
        number += 1

    answers.remember_colours(projects_folder, layers)
    if not shown_once:                                    # all answers were saved: show the stack one time
        ui.stack_drawing(layers)
    save_stack_image(layers, os.path.join(project_folder, "4_stack.png"))
    ui.show_path("Stack image:", os.path.join(project_folder, "4_stack.png"))
    return layers
