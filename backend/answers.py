"""
The answers of the user.

  - answer():   return a saved answer, or ask the question and save the new answer.
  - going back: the user pushes Esc or the Back button (GoBack); HISTORY holds the answers of this run, in order.
  - parsing:    read the answer texts ("Ti 25 nm, Pt 150 nm", "A, B", "150 nm").
  - stack.yaml: read_stack() and write_stack().

Inside the script, the answers are one flat dictionary ("layer 2 materials": "Ti 25 nm, Pt 150 nm"),
because the questions and "go back" use one name for each answer.
"""
import json
import os
import re


# ───────────────────────────────────────────────────────── going back ──

class GoBack(Exception):
    """The user pushed Esc or the Back button: go back to the last question."""


class Stop(Exception):
    """A problem that ends the run (example: Blender stopped with an error). The front end shows the message: the
    window shows its end screen (with Start again), the terminal prints the message. A problem that a new answer can
    repair does not stop the run: the step shows a warning and asks the question again (see forget)."""


class GoToStep(Exception):
    """The user selected a step: a click on the step list of the window, or F1 to F5 in the terminal."""

    def __init__(self, step):
        super().__init__(step)
        self.step = step                                # 1 to 5


HISTORY = []        # the answers of this run, in order: (step number, stack name)
CURRENT_STEP = 0    # flow.py sets this number before each step
SAVE = None         # flow.py sets this function: it writes the answers into stack.yaml after each answer
PREVIOUS = {}       # the old answers of the part that the user changes: the questions show them as default answers



# ───────────────────────────────────────────────────────── parsing ──

def split_layers(text):
    """"A, B" -> ["A", "B"]; "none" -> []."""
    return [] if text == "none" else [name.strip() for name in text.split(",") if name.strip()]


def shown(thickness):
    """Thickness text for the screen and the image: "3 um" -> "3 µm"."""
    number, unit = thickness.split()
    return f"{number} {'µm' if unit == 'um' else unit}"


def thickness_in_mm(text):
    """Change a thickness text ("150 nm", "3 um", "3 µm", "0.5 mm") to mm. Return None for a bad text."""
    match = re.fullmatch(r"\s*([0-9]*\.?[0-9]+)\s*(nm|um|µm|mm)\s*", text.lower())
    if not match:
        return None
    value, unit = float(match.group(1)), match.group(2)
    return value * {"nm": 1e-6, "um": 1e-3, "µm": 1e-3, "mm": 1.0}[unit]


MATERIAL_PATTERN = r"\s*(.+?)\s+([0-9]*\.?[0-9]+)\s*(nm|um|µm|mm)\s*"


def parse_materials(text):
    """"Ti 25 nm, Pt 150 nm" -> [("Ti", "25 nm"), ("Pt", "150 nm")]. Return None for a bad text."""
    out = []
    for item in text.split(","):
        match = re.fullmatch(MATERIAL_PATTERN, item, flags=re.IGNORECASE)
        if not match:
            return None
        name, number, unit = match.group(1), match.group(2), match.group(3).lower()
        if float(number) <= 0:
            return None
        out.append((name, f"{number} {'um' if unit == 'µm' else unit}"))
    return out


def split_colour(text):
    """"#d99a2b 40%" -> ("#d99a2b", 40). With no transparency: "#d99a2b" -> ("#d99a2b", 0)."""
    parts = text.split()
    return parts[0], int(parts[1].rstrip("%")) if len(parts) > 1 else 0


def join_colour(colour, transparency):
    """("#d99a2b", 40) -> "#d99a2b 40%". With no transparency: "#d99a2b"."""
    return f"{colour} {transparency}%" if transparency else colour


def read_colour(text):
    """Read a typed colour: "gold", "#e3b04b" or "#e3b04b 40%" (40 % transparent, at most 90 %).
    Return (hex code, transparency in %), or None for a bad text."""
    from matplotlib.colors import is_color_like, to_hex
    parts = (text or "").split()
    transparency = 0
    if len(parts) > 1 and parts[-1].endswith("%"):
        number = parts.pop()[:-1]
        if not number.isdigit() or int(number) > 90:
            return None
        transparency = int(number)
    name = " ".join(parts)
    return (to_hex(name), transparency) if name and is_color_like(name) else None


# ───────────────────────────────────────────────────────── the colour of each material ──
# The last colour of each material, for all designs: material_colours.yaml in the projects folder. A material with
# no colour in this stack gets its last colour as the default answer (example: Pt is grey in each new design).

COLOURS_FILE = "material_colours.yaml"


def remembered_colours(projects_folder):
    """{material: colour} from the colours file of the projects folder. A missing or bad file gives {}."""
    import yaml
    try:
        with open(os.path.join(projects_folder, COLOURS_FILE), encoding="utf8") as f:
            data = yaml.safe_load(f) or {}
    except (OSError, yaml.YAMLError):
        return {}
    if not isinstance(data, dict):
        return {}
    return {str(name): str(colour) for name, colour in data.items() if read_colour(str(colour))}


def remember_colours(projects_folder, layers):
    """Keep the colour of each material of the stack in the colours file (the last colour wins). layers = the
    layers of step 3, each with materials [{name, colour, transparency}]. The write is atomic, as in write_stack."""
    import yaml
    colours = remembered_colours(projects_folder)
    for layer in layers:
        for m in layer["materials"]:
            colours[m["name"]] = join_colour(m["colour"], m["transparency"])
    os.makedirs(projects_folder, exist_ok=True)
    path = os.path.join(projects_folder, COLOURS_FILE)
    with open(path + ".tmp", "w", encoding="utf8") as f:
        f.write("# Neuro Blender: the last colour of each material. It is the default colour in new designs.\n")
        yaml.safe_dump(dict(sorted(colours.items())), f, allow_unicode=True)
    os.replace(path + ".tmp", path)


# ───────────────────────────────────────────────────────── stack file ──
#
# The stack file (stack.yaml) has 3 parts:
#   design:  the DXF file, its unit, the outline layer and the device number;
#   layers:  the layers from the bottom up, each with its materials;
#   render:  the part of the device to show and the camera angles.
# Inside the script, the answers are one flat dictionary ("layer 2 materials": "Ti 25 nm, Pt 150 nm"),
# because the questions and "go back" use one name for each answer. read_stack and write_stack
# change between the two forms.

STACK_HEADER = """# Neuro Blender stack file.
# Neuro Blender writes your answers here. You can change a value with a text editor.
# Remove a value, and the tool asks that question again at the next run.
"""

DESIGN_KEYS = ["unit", "outline layer", "device number"]
# The format of stack.yaml. Change it (and add a conversion in CONVERSIONS) when the meaning of a value changes.
FORMAT = 2


def convert_1_to_2(data):
    """Format 1 (no "format" value) -> 2: the dashed lines were true / false; now all / some / none.
    (Format 1 also kept the full path of the mask file. Format 2 does not: a shared file must not show it.)"""
    render = data.get("render") or {}
    if isinstance(render.get("guide lines"), bool):
        render["guide lines"] = "all" if render["guide lines"] else "none"
    return data


CONVERSIONS = {1: convert_1_to_2}     # {old format: function that changes it to the next format}
LIST_KEYS = ["through holes"]               # design answers that are lists of mask layers
MAP_KEYS = ["layer names"]                  # design answers that are tables (GDS layer number -> name)
# The render answers: {key in the program: (name in stack.yaml, kind)}. Kind: "text", "yes/no" (true / false in
# the file), "number", or "list" (a list of names: mask layers, file kinds). A new render answer needs only one line
# here.
# (The camera is different: two numbers, saved as "camera: {turn, height}".)
RENDER = {
    "render view": ("view", "text"),
    "render small electrodes larger": ("small electrodes larger", "yes/no"),
    "render guide lines": ("guide lines", "text"),
    "render labels": ("labels", "yes/no"),
    "render background": ("background", "text"),
    "render cleave angle": ("cleave angle", "number"),
    "render space between layers": ("space between layers", "number"),
    "render coating distance": ("coating distance", "number"),
    "render electrode openings": ("electrode openings", "list"),
    "render keep files": ("keep files", "list"),
}


def yes_no(value):
    """YAML true/false (or yes/no text) -> "yes" / "no"."""
    return "yes" if value is True or str(value).lower() in ("yes", "y", "true") else "no"


def forget(stack, key):
    """Remove an answer, so that its question comes again. The old answer is the default answer."""
    if key in stack:
        PREVIOUS[key] = stack.pop(key)
    HISTORY[:] = [(step, k) for step, k in HISTORY if k != key]


def answer(stack, key, ask_function, is_valid=lambda value: True):
    """Return the saved answer stack[key]. If there is no good saved answer, ask the question and save it.
    Each new answer goes into HISTORY, so that the user can go back to it."""
    if key in stack and is_valid(stack[key]):
        return stack[key]
    stack[key] = str(ask_function())
    HISTORY.append((CURRENT_STEP, key))
    if SAVE:
        SAVE(stack)                                     # an answer is never lost, also if the user stops the script
    return stack[key]


def read_stack(path):
    """Read stack.yaml. Return the flat dictionary of answers. No file = an empty dictionary.
    An older format is converted (CONVERSIONS). A file that YAML cannot read stops the tool with its line number."""
    import yaml
    if not os.path.exists(path):
        return {}
    try:
        with open(path, encoding="utf8") as f:
            data = yaml.safe_load(f) or {}
    except yaml.YAMLError as error:
        mark = getattr(error, "problem_mark", None)
        where = f" (line {mark.line + 1})" if mark else ""
        raise Stop(f"Cannot read {path}{where}. Correct it with a text editor, or remove it to start new answers.")
    version = data.get("format", 1)
    if version > FORMAT:
        raise Stop(f"{path} comes from a newer version of Neuro Blender (format {version}). Update the tool.")
    while version < FORMAT:
        data = CONVERSIONS[version](data)
        version += 1
    flat = {}
    if (data.get("design") or {}).get("dxf file"):          # format 1 only: for the project check (flow.py)
        flat["dxf file"] = str(data["design"]["dxf file"])
    for key in DESIGN_KEYS:
        if data.get("design", {}).get(key) is not None:
            flat[key] = str(data["design"][key])
    for key in LIST_KEYS:
        if key in (data.get("design") or {}):
            flat[key] = ", ".join(data["design"][key] or []) or "none"
    for key in MAP_KEYS:
        if isinstance((data.get("design") or {}).get(key), dict):
            flat[key] = json.dumps({str(k): str(v) for k, v in data["design"][key].items()})

    layers = data.get("layers") or []
    for n, layer in enumerate(layers, start=1):
        key = f"layer {n}"
        for name in ("name", "type", "shape", "surface"):
            if layer.get(name) is not None:
                flat[f"{key} {name}"] = str(layer[name])
        materials = layer.get("materials") or []
        if materials and all(m.get("material") and m.get("thickness") for m in materials):
            flat[f"{key} materials"] = ", ".join(f"{m['material']} {m['thickness']}" for m in materials)
            if all(m.get("colour") for m in materials):
                flat[f"{key} colours"] = ", ".join(
                    join_colour(str(m["colour"]), int(str(m.get("transparency") or 0).rstrip("% "))) for m in materials)
        if "openings" in layer:
            openings = layer["openings"] or []
            flat[f"{key} openings"] = ", ".join(openings) if openings else "none"
        if layer.get("cleave") is not None:
            flat[f"{key} cleave"] = yes_no(layer["cleave"])
        if n < len(layers):
            flat[f"{key} has a layer on top"] = "yes"
        elif data.get("layers finished") is not None:
            flat[f"{key} has a layer on top"] = "no" if data["layers finished"] else "yes"

    render = data.get("render") or {}
    for flat_key, (yaml_key, kind) in RENDER.items():
        if kind == "list" and yaml_key in render:
            flat[flat_key] = ", ".join(render[yaml_key] or []) or "none"
        elif kind != "list" and render.get(yaml_key) is not None:
            value = render[yaml_key]
            flat[flat_key] = yes_no(value) if isinstance(value, bool) else str(value)
    camera = render.get("camera") or {}
    if camera.get("turn") is not None and camera.get("height") is not None:
        flat["render camera turn and height"] = f"{camera['turn']}, {camera['height']}"
    return flat


class OneLine(dict):
    """A dictionary that the YAML file shows on one line: {material: Ti, thickness: 25 nm, colour: '#8c857b'}."""


class OneLineList(list):
    """A list that the YAML file shows on one line: [OPENINGS_ELECTRODES, OPENINGS_PADS]."""


def _dumper():
    import yaml

    class Dumper(yaml.SafeDumper):
        pass
    Dumper.add_representer(OneLine, lambda d, v: d.represent_mapping("tag:yaml.org,2002:map", v.items(), flow_style=True))
    Dumper.add_representer(OneLineList, lambda d, v: d.represent_sequence("tag:yaml.org,2002:seq", v, flow_style=True))
    return Dumper


def write_stack(path, flat):
    """Write the flat dictionary of answers into stack.yaml.
    The write is atomic: first a temporary file, then one replace. A stop during the write (example: the window
    closes) cannot leave an empty or half file. The full path of the mask file is not written (the file can be
    shared); flow.py keeps it in mask_file.txt."""
    import yaml
    os.makedirs(os.path.dirname(path), exist_ok=True)
    data = {"format": FORMAT, "design": {k: flat[k] for k in DESIGN_KEYS if k in flat}}
    for key in LIST_KEYS:
        if key in flat:
            data["design"][key] = OneLineList(split_layers(flat[key]))
    for key in MAP_KEYS:
        if key in flat:
            data["design"][key] = json.loads(flat[key])
    if "device number" in data["design"]:
        data["design"]["device number"] = int(data["design"]["device number"])

    layers, n = [], 1
    while any(k.startswith(f"layer {n} ") for k in flat):
        key = f"layer {n}"
        get = lambda name: flat.get(f"{key} {name}")
        layer = {name: get(name) for name in ("name", "type", "shape") if get(name) is not None}
        if get("materials") and parse_materials(get("materials")):
            colours = [c.strip() for c in get("colours").split(",")] if get("colours") else []
            layer["materials"] = []
            for i, (m, t) in enumerate(parse_materials(get("materials"))):
                material = OneLine(material=m, thickness=t)
                if i < len(colours):
                    material["colour"], transparency = split_colour(colours[i])
                    if transparency:
                        material["transparency"] = f"{transparency}%"
                layer["materials"].append(material)
        if get("openings") is not None:
            layer["openings"] = OneLineList(split_layers(get("openings")))
        if get("cleave") is not None:
            layer["cleave"] = get("cleave") == "yes"
        if get("surface") is not None:
            layer["surface"] = get("surface")
        layers.append(layer)
        n += 1
    data["layers"] = layers
    if layers and f"layer {len(layers)} has a layer on top" in flat:
        data["layers finished"] = flat[f"layer {len(layers)} has a layer on top"] == "no"

    render = {}
    for flat_key, (yaml_key, kind) in RENDER.items():
        if flat_key not in flat:
            continue
        value = flat[flat_key]
        if kind == "yes/no":
            render[yaml_key] = value == "yes"
        elif kind == "number":
            number = float(value)
            render[yaml_key] = int(number) if number == int(number) else number
        elif kind == "list":
            render[yaml_key] = OneLineList(split_layers(value))
        else:
            render[yaml_key] = value
    if "render camera turn and height" in flat:
        turn, height = (int(v) for v in flat["render camera turn and height"].split(","))
        render["camera"] = dict(turn=turn, height=height)
    if render:
        data["render"] = render

    temporary = path + ".tmp"
    with open(temporary, "w", encoding="utf8") as f:
        f.write(STACK_HEADER + "\n")
        yaml.dump(data, f, Dumper=_dumper(), sort_keys=False, allow_unicode=True, default_flow_style=False, width=120)
    os.replace(temporary, path)
