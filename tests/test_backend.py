"""
Test the logic of the back end: no window, no terminal questions, no Blender.

Run:  python tests/test_backend.py
Each line shows PASS or FAIL. At the end, the script shows the number of failures.
"""
import os
import sys
import tempfile

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)

from shapely.geometry import Point, Polygon, box
from shapely.ops import unary_union

from backend import answers, ui
from backend.step1_read_mask import DXF_UNITS, UNIT_IN_MM, join_pieces, to_mm
from backend.step4_build_scene import LOOK, bend_groups, drawn_thickness, edge_radius, wrap_pieces

RESULTS = []


def check(name, condition):
    RESULTS.append((name, bool(condition)))


# ── reading the answers ──
check("materials: one line with 3 materials",
      answers.parse_materials("Ti 25 nm, Pt 150 nm, Ti 25 nm") == [("Ti", "25 nm"), ("Pt", "150 nm"), ("Ti", "25 nm")])
check("materials: µm becomes um", answers.parse_materials("PI 5 µm") == [("PI", "5 um")])
check("materials: a bad text is refused", answers.parse_materials("Ti/Pt") is None)
check("materials: a zero thickness is refused", answers.parse_materials("Ti 0 nm") is None)
check("thickness: 150 nm in mm", abs(answers.thickness_in_mm("150 nm") - 1.5e-4) < 1e-12)
check("thickness: 3 um in mm", abs(answers.thickness_in_mm("3 um") - 0.003) < 1e-12)
check("layers: 'A, B' -> ['A', 'B']", answers.split_layers("A, B") == ["A", "B"])
check("layers: 'none' -> []", answers.split_layers("none") == [])
check("colour: a name", answers.read_colour("gold") == ("#ffd700", 0))
check("colour: a hex code with a transparency", answers.read_colour("#d99a2b 40%") == ("#d99a2b", 40))
check("colour: more than 90 % transparency is refused", answers.read_colour("gold 95%") is None)
check("colour: a bad colour is refused", answers.read_colour("not a colour") is None)
check("colour: split and join", answers.join_colour(*answers.split_colour("#d99a2b 40%")) == "#d99a2b 40%")

# ── the answers file: write, then read again ──
flat = {
    "dxf file": "C:/designs/implant.dxf", "unit": "um", "outline layer": "OUTLINE", "device number": "2",
    "through holes": "HOLES",
    "layer 1 name": "Bottom PI", "layer 1 type": "encapsulation", "layer 1 shape": "OUTLINE",
    "layer 1 materials": "PI 5 um", "layer 1 colours": "#d99a2b 40%", "layer 1 openings": "none",
    "layer 1 cleave": "yes", "layer 1 has a layer on top": "yes",
    "layer 2 name": "Tracks", "layer 2 type": "tracks", "layer 2 shape": "METAL",
    "layer 2 materials": "Ti 20 nm, Au 200 nm", "layer 2 colours": "#8c857b, #e3b04b", "layer 2 surface": "shiny",
    "layer 2 has a layer on top": "no",
    "render view": "electrodes", "render guide lines": "none", "render labels": "yes", "render cleave angle": "9",
    "render space between layers": "1.5", "render coating distance": "20", "render camera turn and height": "32, 11",
    "render electrode openings": "OPEN_E",
}
with tempfile.TemporaryDirectory() as folder:
    file = os.path.join(folder, "stack.yaml")
    answers.write_stack(file, flat)
    again = answers.read_stack(file)
    text = open(file, encoding="utf8").read()
check("answers file: all the answers come back the same",
      all(again.get(k) == v for k, v in flat.items() if k != "dxf file"))
check("answers file: the full path of the mask file is not in the file (it can be shared)", "implant.dxf" not in text)
check("answers file: the file has a format version", text.splitlines()[4] == "format: 2")
check("answers file: the transparency is a separate value", "transparency: 40%" in text)
check("answers file: the cleave angle is a number", "cleave angle: 9\n" in text)

with tempfile.TemporaryDirectory() as folder:
    file = os.path.join(folder, "stack.yaml")
    with open(file, "w", encoding="utf8") as f:                # format 1: no format value, true / false lines
        f.write("design:\n  dxf file: C:/old/implant.dxf\n  unit: um\nrender:\n  guide lines: true\n")
    old = answers.read_stack(file)
    check("answers file: format 1 is converted (dashed lines true -> all)", old.get("render guide lines") == "all")
    check("answers file: format 1 still gives the old mask path (for the project check)",
          old.get("dxf file") == "C:/old/implant.dxf")
    with open(file, "w", encoding="utf8") as f:
        f.write("format: 99\n")
    try:
        answers.read_stack(file)
        newer = False
    except answers.Stop:
        newer = True
    check("answers file: a file from a newer version gives a clear stop", newer)
    with open(file, "w", encoding="utf8") as f:
        f.write("design:\n  unit: [um\n")                  # broken YAML
    try:
        answers.read_stack(file)
        message = ""
    except answers.Stop as stop:
        message = str(stop)
    check("answers file: a broken file gives its line number", "line" in message)
    answers.write_stack(file, {"unit": "um"})
    check("answers file: no temporary file stays after the write", os.listdir(folder) == ["stack.yaml"])

# ── mask layer names with a comma (allowed in DXF) would break the lists "A, B" ──
from backend.step1_read_mask import without_commas

ui.use(type("Silent", (), {"note": lambda self, text: None})())
renamed = without_commas({"OPEN, ELECTRODES": {"closed": [], "open": []}, "METAL": {"closed": [], "open": []}})
check("names: a comma in a mask layer name changes to ';'", list(renamed) == ["OPEN; ELECTRODES", "METAL"])

# ── shared helpers: the thickness text, and the colour mix of the theme (theme.py has no window code) ──
from backend.answers import shown
from frontends.theme import mix

check("thickness text: um shows as µm, other units stay", (shown("3 um"), shown("150 nm")) == ("3 µm", "150 nm"))
check("colour mix: 1 = the colour, 0 = the background, 0.5 = the middle",
      (mix("#ff0000", "#ffffff", 1), mix("#ff0000", "#FFFFFF", 0), mix("#000000", "#ffffff", 0.5))
      == ("#ff0000", "#ffffff", "#808080"))

# The terminal grey must be readable on a white and on a dark terminal (the terminal does not tell its background).
from frontends.theme import GREY


def contrast(a, b):
    """Contrast ratio of two hex colours (WCAG 2): 1 = the same, 21 = black on white."""
    def luminance(colour):
        c = [int(colour[i:i + 2], 16) / 255 for i in (1, 3, 5)]
        c = [x / 12.92 if x <= 0.03928 else ((x + 0.055) / 1.055) ** 2.4 for x in c]
        return 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2]
    high, low = sorted([luminance(a), luminance(b)], reverse=True)
    return (high + 0.05) / (low + 0.05)


check("terminal grey: contrast 4:1 or more on white, Windows Terminal and VS Code backgrounds",
      min(contrast(GREY, back) for back in ("#ffffff", "#0c0c0c", "#1e1e1e")) >= 4.0)

# The steps: one list in the back end; ui.header(step) sends the number and the title of the step.
headers = []
ui.use(type("Headers", (), {"header": lambda self, step, title: headers.append((step, title))})())
ui.header(2)
check("steps: ui.header(2) sends the title of step 2 from the one list", headers == [(2, ui.STEPS[1][1])] and
      [name for name, _ in ui.STEPS] == ["File", "Device", "Stack", "Render", "Labels"])

# Questions as data (CR-07): the questions of a layer, their conditions and their checks.
from backend.step3_layer_questions import layer_questions

below_tracks = layer_questions(1, None, ["OUTLINE", "OPEN"], {}, "OUTLINE", {}, old={})
needed = lambda kind: [q.key.split(" ", 2)[2] for q in below_tracks if q.needed({"layer 1 type": kind})]
check("questions: an encapsulation layer has openings and cleave, no surface",
      needed("encapsulation") == ["name", "type", "shape", "materials", "colours", "openings", "cleave"])
check("questions: a tracks layer has a surface, no openings", needed("tracks")[-1] == "surface"
      and "openings" not in needed("tracks"))
openings = below_tracks[5]
check("questions: openings check refuses no tick, 'none' with a layer, an unknown layer; accepts 'none' and 'OPEN'",
      [openings.check(v) is None for v in ("", "none, OPEN", "OTHER", "none", "OPEN")] == [False] * 3 + [True] * 2)
check("questions: colours need one good colour for each material",
      below_tracks[4].check("#8c857b, #e3b04b", {"layer 1 materials": "Ti 20 nm, Au 200 nm"}) is None
      and below_tracks[4].check("#8c857b", {"layer 1 materials": "Ti 20 nm, Au 200 nm"}) is not None)

# Step 3 in a form (the window): the form opens only when an answer is missing; the answers come back in the
# standard form, and Back from step 4 comes back to the form.
from backend import step3_layer_questions as step3


class FormFront:
    SHOWS_FORMS = True

    def __init__(self, change=None):
        self.opened, self.change = [], change

    def edit_stack(self, layers, make_questions, problems, open_layer=None):
        self.opened.append([dict(layer) for layer in layers])
        self.open_layer = open_layer
        result = [{k: v for k, v in layer.items() if k != "has a layer on top"} for layer in layers]
        return self.change(result) if self.change else result

    def __getattr__(self, name):
        return lambda *values, **options: None


form_device = {name: {"closed": [[(0, 0), (1, 0), (1, 1)]], "open": []} for name in ("OUTLINE", "METAL")}
form_stack = {"outline layer": "OUTLINE",
              "layer 1 name": "Bottom PI", "layer 1 type": "encapsulation", "layer 1 shape": "OUTLINE",
              "layer 1 materials": "PI 5 um", "layer 1 colours": "#d99a2b", "layer 1 openings": "none",
              "layer 1 cleave": "yes", "layer 1 has a layer on top": "yes",
              "layer 2 name": "Tracks", "layer 2 type": "tracks", "layer 2 shape": "METAL",
              "layer 2 materials": "Au 200 nm", "layer 2 colours": "#e3b04b", "layer 2 surface": "shiny",
              "layer 2 has a layer on top": "no"}
answers.HISTORY.clear()
answers.PREVIOUS.clear()
with tempfile.TemporaryDirectory() as temp:
    front = FormFront()
    ui.use(front)
    step3.run(form_device, dict(form_stack), temp)
    check("stack form: all answers saved and good: no form", front.opened == [])

    answers.PREVIOUS.update({k: form_stack[k] for k in form_stack if k.startswith("layer 2 ")})   # go to step 3
    changed = dict(form_stack)
    for key in list(answers.PREVIOUS):
        changed.pop(key)
    front = FormFront(change=lambda layers: [layers[0], dict(layers[1], materials="Au 300 µm")])
    ui.use(front)
    layers = step3.run(form_device, changed, temp)
    check("stack form: a removed answer opens the form with the old answers, at the changed layer",
          len(front.opened) == 1 and front.opened[0][1]["materials"] == "Au 200 nm" and front.open_layer == 1)
    check("stack form: the answers are saved in the standard form; Back from step 4 comes to the form",
          changed["layer 2 materials"] == "Au 300 um" and layers[1]["materials"][0]["thickness"] == "300 um"
          and changed["layer 2 has a layer on top"] == "no" and answers.HISTORY[-1][1] == "layer 2 has a layer on top"
          and not answers.PREVIOUS)
answers.HISTORY.clear()

# A page of questions (step 4 before the 3D build) in a form: no form when the answers are there; else one form with
# the saved answers; the answers are saved, and Back from the next question comes back to the form.
from backend.questions import Question, answer_page


class PageFront(FormFront):
    def ask_page(self, help_text, questions, values):
        self.opened.append(dict(values))
        return {"render cleave angle": "12", "render space between layers": "4"}


page = [Question("render cleave angle", "number", "Cleave angle?", options=(0, 45), default="9"),
        Question("render space between layers", "number", "Space?", options=(0, 100), default="0")]
check("page: a number out of its range is refused", page[0].check("50") and page[0].check("x") and not page[0].check("9.5"))
front = PageFront()
ui.use(front)
page_stack = {"render cleave angle": "9", "render space between layers": "0"}
check("page: all answers there: no form", answer_page(page_stack, page) == page_stack and front.opened == [])
page_stack.pop("render space between layers")
values = answer_page(page_stack, page)
check("page: a missing answer opens one form with the saved answers; the new answers are saved",
      front.opened == [{"render cleave angle": "9"}] and page_stack == values == {"render cleave angle": "12",
                                                                               "render space between layers": "4"}
      and answers.HISTORY[-1][1] == "render space between layers")
answers.HISTORY.clear()

# ── units ──
check("units: only nm, µm, mm and cm", set(UNIT_IN_MM) == {"nm", "um", "mm", "cm"})
check("units: a DXF file in metre or inch has no unit for the tool", 6 not in DXF_UNITS and 1 not in DXF_UNITS)
check("units: µm to mm", to_mm({"A": {"closed": [[(1000, 0)]], "open": []}}, "um")["A"]["closed"][0][0] == (1.0, 0.0))

# ── GDS: pieces of one polygon that touch become one shape ──
joined = join_pieces([[(0, 0), (1, 0), (1, 1), (0, 1)], [(1, 0), (2, 0), (2, 1), (1, 1)]])
check("GDS: two touching pieces become one shape", len(joined) == 1 and abs(Polygon(joined[0]).area - 2) < 1e-9)

# ── reading a DXF file: the same design gives the same shapes in µm and in mm ──
import ezdxf
from backend.step1_read_mask import read_dxf

counts = {}
with tempfile.TemporaryDirectory() as temp:
    for unit, scale, code in (("um", 1000.0, 13), ("mm", 1.0, 4)):
        doc = ezdxf.new()
        doc.header["$INSUNITS"] = code
        msp = doc.modelspace()
        msp.add_lwpolyline([(0, 0), (15 * scale, 0), (15 * scale, 3 * scale), (0, 3 * scale)], close=True,
                           dxfattribs={"layer": "OUTLINE"})
        msp.add_circle((1 * scale, 1 * scale), 0.1 * scale, dxfattribs={"layer": "OPENINGS"})   # radius 100 µm
        file = os.path.join(temp, f"design_{unit}.dxf")
        doc.saveas(file)
        counts[unit] = len(read_dxf(file)[1]["OPENINGS"]["closed"][0])
check("DXF: a circle gives the same number of points in µm and in mm", counts["um"] == counts["mm"])
check("DXF: a circle with radius 100 µm on a 15 mm drawing gets 16 to 200 points", 16 <= counts["um"] <= 200)

# ── layer images: one image for each layer, also for a layer with only open lines or with no shapes ──
from backend import run_cache as image_cache
from backend.step1_read_mask import save_layer_images

ui.use(type("Silent", (), {"show_path": lambda self, *values: None})())
image_cache.clear()
with tempfile.TemporaryDirectory() as temp:
    save_layer_images({"OUTLINE": {"closed": [[(0, 0), (4, 0), (4, 2), (0, 2)]], "open": []},
                       "LINES": {"closed": [], "open": [[(1, 1), (3, 1)]]},
                       "EMPTY": {"closed": [], "open": []}}, temp)
    check("layer images: one image for each layer (also open lines only, and no shapes)",
          sorted(os.listdir(temp)) == ["01_OUTLINE.png", "02_LINES.png", "03_EMPTY.png"])
image_cache.clear()

# ── the tolerances of the scene come from the device width, not from fixed mm values ──
from backend.step4_build_scene import precision, to_json

check("precision: a 1.2 mm device keeps details above 0.24 µm, with 6 decimals", precision(1.2) == (1.2 * 2e-4, 6))
tiny = Polygon([(0, 0), (0.005, 0), (0.005, 0.005), (0.0026, 0.005), (0.0025, 0.0052), (0.0024, 0.005),
                (0, 0.005)])                                     # a 5 µm device with a 0.2 µm tip
kept = to_json([tiny], *precision(0.005))[0]["exterior"]
check("precision: a 0.2 µm detail of a 5 µm device stays (a fixed 0.5 µm tolerance removed it)", len(kept) == 7)

# ── the shapes of one device (step 2) ──
from backend.step2_pick_device import shapes_inside

device = box(0, 0, 10, 4)
mask = {"OUTLINE": {"closed": [list(device.exterior.coords)], "open": []},
        "WAFER": {"closed": [list(box(-50, -50, 50, 50).exterior.coords)], "open": []},   # covers the device
        "METAL": {"closed": [list(box(2, 1, 8, 2).exterior.coords),          # inside the outline
                             list(box(5, 3, 7, 9).exterior.coords),          # crosses the outline (to a bus line)
                             list(box(20, 0, 22, 4).exterior.coords)],       # another device: outside
                  "open": []}}
kept, cut = shapes_inside(mask, device)
metal = [Polygon(ring) for ring in kept["METAL"]["closed"]]
check("device shapes: a shape inside the outline stays", any(abs(p.area - 6) < 1e-9 for p in metal))
check("device shapes: a shape that crosses the outline is cut, not removed",
      any(abs(p.area - 2) < 1e-9 for p in metal) and cut == {"METAL": 1})
check("device shapes: a shape outside the outline goes", len(metal) == 2)
check("device shapes: a shape that covers the device becomes the device shape, with no warning",
      abs(Polygon(kept["WAFER"]["closed"][0]).area - device.area) < 1e-9 and "WAFER" not in cut)

# ── the project folder of a mask file: two files with the same name get two folders ──
from backend import flow as flow_module

saved_projects = flow_module.PROJECTS
notes, replies = [], []
ui.use(type("Small", (), {"note": lambda self, text: notes.append(text),                # keeps the notes
                          "ask_yes_no": lambda self, question, help_text, default: replies.pop(0)})())
with tempfile.TemporaryDirectory() as temp:
    flow_module.PROJECTS = os.path.join(temp, "projects")
    for folder in ("a", "b"):
        os.makedirs(os.path.join(temp, folder))
        open(os.path.join(temp, folder, "wafer.dxf"), "w").close()
    file_a, file_b = os.path.join(temp, "a", "wafer.dxf"), os.path.join(temp, "b", "wafer.dxf")
    folder_a = flow_module.project_folder_for(file_a)
    replies.append("no")                                       # "Is this the same design?" no
    folder_b = flow_module.project_folder_for(file_b)
    check("project: the first file gets projects/<name>", os.path.basename(folder_a) == "wafer")
    check("project: another file with the same name gets another folder",
          folder_b != folder_a and os.path.basename(folder_b).startswith("wafer_") and len(notes) == 1)
    check("project: the same file again gets its own folder again",
          flow_module.project_folder_for(file_a) == folder_a and flow_module.project_folder_for(file_b) == folder_b)
    os.remove(file_a)
    file_c = os.path.join(temp, "wafer.dxf")                  # file a was moved here
    open(file_c, "w").close()
    check("project: a moved file keeps the project of its old place", flow_module.project_folder_for(file_c) == folder_a)
    file_d = os.path.join(temp, "b", "copy", "wafer.dxf")      # a copy of the design
    os.makedirs(os.path.dirname(file_d))
    open(file_d, "w").close()
    replies.append("yes")                                      # "Is this the same design?" yes
    check("project: the same design in another file uses the old project (answer yes)",
          flow_module.project_folder_for(file_d) == folder_a and not replies)
flow_module.PROJECTS = saved_projects

# ── drawn thickness ──
layers = [dict(type="encapsulation", materials=[dict(name="PI", thickness="5 um")]),
          dict(type="tracks", materials=[dict(name="Ti", thickness="20 nm"), dict(name="Au", thickness="200 nm")]),
          dict(type="encapsulation", materials=[dict(name="PI", thickness="5 um")])]
drawn = drawn_thickness(layers, width=1.0)
pi, ti, au = drawn[id(layers[0]["materials"][0])], drawn[id(layers[1]["materials"][0])], drawn[id(layers[1]["materials"][1])]
check("thickness: the polymer is drawn thicker than the metal layer", pi > ti + au)
check("thickness: the thin Ti film gets at least 20 % of its layer", ti / (ti + au) >= 0.2 - 1e-9)
check("thickness: the thickest layer has the largest drawn thickness", abs(pi - LOOK["thickest_layer"]) < 1e-9)

# ── a stack that breaks a rule is refused in step 3, at the answer ──
from backend import step3_layer_questions

check("stack rules: a stack with no tracks layer is a problem",
      step3_layer_questions.check_stack([dict(type="encapsulation")]) != [])
stack_answers = {"layer 1 name": "PI", "layer 1 type": "encapsulation", "layer 1 shape": "OUTLINE",
                 "layer 1 materials": "PI 5 um", "layer 1 colours": "#d99a2b", "layer 1 openings": "none",
                 "layer 1 cleave": "yes", "layer 1 has a layer on top": "no"}           # saved: no tracks layer
asked = []


class AskedAgain(Exception):
    """The test front end got a question: the test stops there."""


def stop_at_question(self, question, help_text, default):
    raise AskedAgain(question)


ui.use(type("Refuse", (), {
    "header": lambda self, *a: None, "note": lambda self, *a: None, "warn": lambda self, text: asked.append(text),
    "stack_drawing": lambda self, *a: None, "show_path": lambda self, *a: None, "section": lambda self, *a: None,
    "ask_yes_no": stop_at_question})())
try:
    step3_layer_questions.run({"OUTLINE": {"closed": [], "open": []}}, dict(stack_answers), tempfile.gettempdir())
    refused = None
except AskedAgain as question:
    refused = str(question)
check("stack rules: step 3 shows the problem and asks 'Add a layer on top?' again",
      refused == "Add a layer on top?" and any("No tracks layer" in w for w in asked))
answers.PREVIOUS.clear()

# ── labels: the label column is wide enough for the longest label ──
from backend.step5_labels import LABEL_COLUMN, column_width, text_width

short = [dict(name="Top PI", text="5 µm")]
long_name = "Electrode coating PEDOT:PSS on IrOx, 2 layers"
check("labels: short labels keep the usual column width", column_width(short, 20, 1000) == int(LABEL_COLUMN * 1000))
check("labels: a long label makes the column wide enough (text never cut)",
      column_width([dict(name=long_name, text="1 µm")], 20, 1000) * 0.92 >= text_width(long_name, 20, bold=True))

# ── the agreement with the Blender script (progress lines, scene format) ──
from backend import blender_protocol

line = blender_protocol.message("built", name="Top PI - PI")
check("Blender link: a progress line is read back", blender_protocol.read(line) == {"event": "built", "name": "Top PI - PI"})
check("Blender link: other Blender output is not a progress line",
      blender_protocol.read("Neuro Blender: built something") is None and blender_protocol.read("Fra:1 Mem:12M") is None)
check("Blender link: a broken progress line is not read", blender_protocol.read(blender_protocol.PREFIX + "{broken") is None)

# ── which layers bend ──
for layer, cleave in zip(layers, ("yes", None, "yes")):
    if cleave:
        layer["cleave"] = cleave
check("cleave: the layer below bends down, the layer above bends up", bend_groups(layers) == {0: (1, -1), 2: (1, 1)})

# ── the encapsulation on the tracks fills the space around the tracks ──
area, track = box(0, 0, 10, 4), box(2, 1.5, 8, 2.5)
pieces = wrap_pieces([area], [([track], 0.3)], bottom=0.1, clearance=0.01, simplify=precision(10)[0])
check("fill: the pieces cover the full layer", abs(sum(p.area for p, _ in pieces) - area.area) < 1e-6)
check("fill: above the track, the bottom is on the top of the track",
      any(abs(z - 0.3) < 1e-9 and p.contains(track.centroid) for p, z in pieces))
check("fill: around the track, the bottom goes down to the bottom of the track",
      any(abs(z - 0.1) < 1e-9 and p.contains(box(0, 0, 1, 1).centroid) for p, z in pieces))

# Random layouts: for any tracks (also tracks that cross each other or the outline, and a layer with an opening),
# the pieces must cover the layer exactly, and each bottom must be the bottom of the tracks or the top of a track.
import random

rng, exact = random.Random(1), True
for case in range(25):
    layer = box(0, 0, 10, 4)
    if case % 5 == 0:
        layer = layer.difference(Point(5, 2).buffer(0.6))          # an opening in the layer
    tracks = [box(x, y, x + rng.uniform(0.05, 3), y + rng.uniform(0.05, 3))
              for x, y in [(rng.uniform(-1, 10), rng.uniform(-1, 4)) for _ in range(rng.randint(1, 8))]]
    pieces = wrap_pieces([layer], [(tracks, 0.3)], bottom=0.1, clearance=0.01, simplify=precision(10)[0])
    exact &= abs(sum(p.area for p, _ in pieces) - layer.area) < 1e-6 and all(z in (0.1, 0.3) for _, z in pieces)
check("fill: 25 random track layouts: the pieces cover the layer exactly", exact)

# ── rounded edges ──
check("round edges: half of the drawn thickness on a wide shape", abs(edge_radius([box(0, 0, 10, 10)], 0.04) - 0.02) < 1e-9)
check("round edges: smaller on a narrow shape", edge_radius([box(0, 0, 10, 0.05)], 0.04) < 0.02)
neck = unary_union([box(0, 0, 1, 1), box(2, 0, 3, 1), box(1, 0.49, 2, 0.51)])     # two squares, a 0.02 wide neck
check("round edges: a narrow neck in a wide shape gets a radius below half the neck width",
      edge_radius([neck], 0.1) < 0.01)
saved_round = LOOK["round_edges"]
LOOK["round_edges"] = 0.0                                      # the user turns the rounded edges off
check("round edges: off (LOOK round_edges = 0) gives radius 0, no error", edge_radius([neck], 0.1) == 0.0)
LOOK["round_edges"] = saved_round

# ── turn of the device: the electrodes at the top, also for a round device ──
from backend.step4_build_scene import orient

ring = Point(0, 0).buffer(2).difference(Point(0, 0).buffer(1.5))                 # a cuff: no long side
round_device = {"OUTLINE": {"closed": [list(ring.exterior.coords), list(ring.interiors[0].coords)], "open": []},
                "COATING": {"closed": [list(Point(1.75, 0).buffer(0.1).exterior.coords)], "open": []}}
change = orient(round_device, [dict(type="electrode coating", shape="COATING")], "OUTLINE")
turned_ring, turned_site = change(ring), change(Point(1.75, 0).buffer(0.1))
check("turn: a round device with its electrodes on the right gets the electrodes at the top",
      turned_site.centroid.y > turned_ring.centroid.y + 1)


# ── the look (colour, transparency, surface) changes no shape: a cached scene gets the new look by paint() ──
import contextlib
import copy

from backend import step1_read_mask, step2_pick_device
from backend.step4_build_scene import build_scene, paint, shape_answers


class SilentFront:
    """Shows nothing. The answers file of the test design gives all the answers."""
    def working(self, text):
        return contextlib.nullcontext()

    def __getattr__(self, name):
        return lambda *values, **options: None


ui.use(SilentFront())
with tempfile.TemporaryDirectory() as temp:
    example = os.path.join(REPO, "tests", "design", "linear_probe.dxf")
    look_stack = answers.read_stack(os.path.join(REPO, "tests", "design", "linear_probe_stack.yaml"))
    look_stack["dxf file"] = example
    device = step2_pick_device.run(step1_read_mask.run(example, look_stack, temp), look_stack, temp)
    look_layers = step3_layer_questions.run(device, look_stack, temp)
recoloured = copy.deepcopy(look_layers)
for layer in recoloured:
    layer["surface"] = "shiny"
    for m in layer["materials"]:
        m["colour"], m["transparency"] = "#123456", 40
scene_old = build_scene(device, look_layers, look_stack, "electrodes", "yes", 9, 0, 20)
scene_new = build_scene(device, recoloured, look_stack, "electrodes", "yes", 9, 0, 20)
painted = copy.deepcopy(scene_old)
paint(painted, recoloured)
check("look: a colour change gives the same shape key", shape_answers(look_layers) == shape_answers(recoloured))
check("look: the old scene with the new colours = a new build with the new colours", painted == scene_new)
check("look: a thickness change gives a new shape key",
      shape_answers([dict(look_layers[0], materials=[dict(look_layers[0]["materials"][0], thickness=9.0)])])
      != shape_answers(look_layers[:1]))

# ── test images of a question: one Blender run; going back with the same answers renders nothing again ──
import matplotlib.pyplot as plt

from backend import step4_build_scene as s4

blender_runs = []


def fake_blender(blender, scene, scene_file, image_file, what="", images=1):   # writes small images, no render
    blender_runs.append(what)
    for test in choice_tests:
        plt.imsave(test["file"], [[0.5, 0.8]])


saved_run_blender, s4.run_blender = s4.run_blender, fake_blender
image_cache.clear()
with tempfile.TemporaryDirectory() as temp:
    choice_tests = [dict(name=f"View {n}", meaning="test", file=os.path.join(temp, f"t{n}.png")) for n in (1, 2)]
    sheet = os.path.join(temp, "choices.png")
    for key in ("scene A", "scene A", None, None, "scene B"):
        s4.render_choices("blender", {}, {}, choice_tests, sheet, os.path.join(temp, "s.json"), "Test", "",
                          cache=("view images", key))
    check("test images: same key again = no new render; no key = always a render",
          len(blender_runs) == 4 and os.path.exists(sheet))
s4.run_blender = saved_run_blender
image_cache.clear()


# ── the view question: the angles of the test views show only after "My own angles" ──
class ViewFront:
    def __init__(self, choice):
        self.choice, self.paths = choice, []

    def ask_choice(self, question, help_text, options, default, details, side):
        return self.choice

    def ask_text(self, question, help_text, default, check_function):
        return "45" if question.startswith("Turn") else "13"

    def show_path(self, text, path, *args, **kwargs):
        self.paths.append(os.path.basename(path))

    def note(self, *args, **kwargs):
        pass


def fake_choices(blender, scene, test_scene, tests, choices_file, *args, **kwargs):
    for test in tests:
        plt.imsave(test["file"], [[0.5, 0.8]])


saved_render_choices, s4.render_choices = s4.render_choices, fake_choices
answers.PREVIOUS.clear()
for choice, expected_angles, expected_file in (("5", (45, 13), True), ("2", (32, 35), False)):
    with tempfile.TemporaryDirectory() as temp:
        view_front = ViewFront(choice)
        ui.use(view_front)
        result = s4.ask_view({}, "blender", temp)
        check(f"view question: choice {choice} gives {expected_angles}; the image with the angles "
              f"{'shows' if expected_file else 'does not show'}",
              result == expected_angles and ("5_view_angles.png" in view_front.paths) == expected_file
              and os.path.exists(os.path.join(temp, "5_view_angles.png")) == expected_file)
s4.render_choices = saved_render_choices


# ── the dashed lines: one choice (none, 6, all), no test images ──
class GuideFront:
    def ask_choice(self, question, help_text, options, default, details, side):
        self.options, self.default = list(options), default
        return default


guide_results = []
for count, old, expected_options, expected_default in ((8, None, ["none", "some", "all"], "some"),
                                                       (3, None, ["none", "all"], "all"),
                                                       (8, "none", ["none", "some", "all"], "none"),
                                                       (3, "some", ["none", "all"], "all")):
    guide_front = GuideFront()
    ui.use(guide_front)
    answers.PREVIOUS.clear()
    if old:
        answers.PREVIOUS["render guide lines"] = old
    result = s4.ask_guides({"guides": {"centres": [(0, 0)] * count}})
    guide_results.append(guide_front.options == expected_options and result == expected_default)
answers.PREVIOUS.clear()
check("dashed lines: none, 6 or all (no '6' with 6 electrodes or fewer); the old answer is the default",
      all(guide_results))

# ── thin strips: an opening that ends a little inside the outline leaves a strip that cannot have round edges ──
strip = box(0, 0, 10, 10).union(box(10, 4.99, 14, 5.01))           # a square with a strip of 0.02 on its side
cleaned = s4.without_slivers([strip], 0.1)
check("thin strips: a strip narrower than two radii goes, the layer stays",
      len(cleaned) == 1 and abs(cleaned[0].area - 100) < 1e-6)
bridge = box(0, 0, 10, 10).difference(box(2, 2, 4.9, 8)).difference(box(5.1, 2, 8, 8))   # two openings, 0.2 apart
check("thin strips: a bridge of 0.2 between two openings stays (radius 0.09)",
      abs(s4.without_slivers([bridge], 0.09)[0].area - bridge.area) < 1e-6)
check("rounded edges: a bridge between two openings narrower than two radii makes the radius smaller",
      s4.edge_radius([bridge], 1.0) < 0.1)

# ── the shared checks of backend/ui.py, with a fake front end ──
class FakeFront:
    """A front end that gives prepared answers and keeps the check functions of the questions."""
    def __init__(self):
        self.answers, self.checks = [], []

    def ask_ticks(self, question, help_text, options, ticked, check_function, side):
        self.checks.append(check_function)
        self.options = options
        return self.answers.pop(0)

    def ask_text(self, question, help_text, default, check_function):
        self.checks.append(check_function)
        return self.answers.pop(0)


front = FakeFront()
ui.use(front)
front.answers = [["none"]]
result = ui.ask_layers(["A", "B"], "Openings?", none_text="no openings")
tick_check = front.checks[-1]
check("ticks: 'no openings' gives 'none'", result == "none")
check("ticks: 'no openings' is the first choice", front.options[0] == ("none", "no openings"))
check("ticks: no tick is refused", tick_check([]) is not None)
check("ticks: 'no openings' with a mask layer is refused", tick_check(["none", "A"]) is not None)
check("ticks: one mask layer is good", tick_check(["A"]) is None)
front.answers = [["A", "B"]]
check("ticks: two mask layers give 'A, B'", ui.ask_layers(["A", "B"], "Openings?") == "A, B")
front.answers = ["7"]
ui.ask_number("Device?", "", 1, 9)
check("number: 12 is refused for 1 to 9", front.checks[-1]("12") is not None)
check("number: 7 is good for 1 to 9", front.checks[-1]("7") is None)
front.answers = ["Ti 25 nm,Pt 150 nm"]
check("materials question: the answer gets the standard form",
      ui.ask_materials("Materials?") == "Ti 25 nm, Pt 150 nm")

# ── going back (Esc, or the Back button), with the real order of the work and a fake front end ──
import contextlib
import shutil

import yaml

from backend import flow, step4_build_scene


class StopTest(Exception):
    """The script of the test is at its end."""


class ScriptedFront:
    """A front end that answers from a script: [(start of the question, answer)]. "BACK" = the user goes back,
    "STOP" = the end of the test. A question that is not in the script gets its default answer."""
    def __init__(self, script):
        self.script, self.asked = list(script), []

    def answer(self, question, default, first=None):
        self.asked.append((question, default))
        if self.script and question.startswith(self.script[0][0]):
            reply = self.script.pop(0)[1]
            if reply == "BACK":
                raise answers.GoBack
            if reply.startswith("GOTO"):
                raise answers.GoToStep(int(reply.split()[1]))
            if reply == "STOP":
                raise StopTest
            return reply
        return default if default not in (None, "") else first

    def header(self, *args): pass
    section = note = warn = success = show_path = show_table = stack_drawing = header

    def working(self, text):
        return contextlib.nullcontext()

    def progress(self, text, total):
        return contextlib.nullcontext()

    def ask_text(self, question, help_text, default, check_function):
        return self.answer(question, default)

    def ask_choice(self, question, help_text, options, default, details, side):
        return self.answer(question, default, next(iter(options)))

    def ask_yes_no(self, question, help_text, default):
        return self.answer(question, "yes" if default == "y" else "no")

    def ask_ticks(self, question, help_text, options, ticked, check_function, side):
        return self.answer(question, ticked)

    def ask_colour(self, question, default):
        return self.answer(question, default)

    def pick_file(self, *args):
        return None


here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
mask = os.path.join(here, "tests", "design", "linear_probe.dxf")
folder = tempfile.mkdtemp()
data = yaml.safe_load(open(os.path.join(here, "tests", "design", "linear_probe_stack.yaml"), encoding="utf8"))
data["layers finished"] = True
data["render"] = {"view": "electrodes", "small electrodes larger": True, "guide lines": "all", "labels": True,
                  "cleave angle": 9, "space between layers": 0, "coating distance": 20,
                  "camera": {"turn": 32, "height": 11}}
os.makedirs(os.path.join(folder, "linear_probe"))
stack_file = os.path.join(folder, "linear_probe", "stack.yaml")
yaml.safe_dump(data, open(stack_file, "w", encoding="utf8"), sort_keys=False)
saved_globals = (flow.PROJECTS, step4_build_scene.find_blender)   # put back at the end of this part
flow.PROJECTS = folder                                       # the results of the test go into a temporary folder
step4_build_scene.find_blender = lambda projects_folder: "blender"   # the test does not render
front = ScriptedFront([
    ("This design has saved answers", "render"), ("Image quality?", "BACK"),          # 1. back from the steps: the start
    ("This design has saved answers", "change"), ("Which part do you want", "view"),
    ("Which part of the device", "BACK"),                                       # 2. back again: the start
    ("This design has saved answers", "change"), ("Which part do you want", "stack"), ("Which layer?", "4"),
    ("Name?", "Coating X"), ("Type?", "BACK"),                                  # 3. back to the last answer
    ("Name?", "STOP")])
ui.use(front)
try:
    flow.run(mask)
except StopTest:
    pass
questions = [q for q, _ in front.asked]
starts = [n for n, q in enumerate(questions) if q.startswith("This design has saved answers")]
check("going back: from 'Image quality?' (no earlier answer in the steps) back to the start",
      questions[starts[1] - 1] == "Image quality?" if len(starts) > 1 else False)
check("going back: from the first view question back to the start", len(starts) == 3)
saved = answers.read_stack(stack_file)
check("going back: the view answers that 'change one part' removed are kept in stack.yaml",
      saved.get("render view") == "electrodes" and saved.get("render camera turn and height") == "32, 11")
names = [default for q, default in front.asked if q == "Name?"]
check("going back: the old answer is the default answer of the question", names[-1:] == ["Coating X"])
view_keys = [k for k in answers.read_stack(stack_file) if k.startswith("render ")]
ui.use(ScriptedFront([("Which part do you want", "view")]))
left = flow.change_one_part(answers.read_stack(stack_file))
check("change one part: 'view' removes all the render answers (from the table, not from a list)",
      len(view_keys) >= 7 and not [k for k in left if k.startswith("render ")]
      and all(k in answers.PREVIOUS for k in view_keys))
answers.PREVIOUS.clear()

# Going to a step: from "Image quality?" (step 4) to step 2. The questions of step 2 and of the later steps come
# again with the old answers as defaults. The terminal has no forms: step 3 keeps its answers (no layer question).
yaml.safe_dump(data, open(stack_file, "w", encoding="utf8"), sort_keys=False)    # a fresh answers file
front = ScriptedFront([("This design has saved answers", "render"), ("Image quality?", "GOTO 2"),
                       ("Image quality?", "STOP")])
ui.use(front)
saved_render_choices, step4_build_scene.render_choices = step4_build_scene.render_choices, lambda *a, **k: None
try:
    flow.run(mask)                                           # (no test images: render_choices does nothing)
except StopTest:
    pass
step4_build_scene.render_choices = saved_render_choices
questions = [q for q, _ in front.asked]
outline = [default for q, default in front.asked if q.startswith("Which mask layer draws the device outline")]
check("going to a step: step 2 asks its questions again, with the old answer as default", outline == ["OUTLINE"])
check("going to a step: in the terminal, step 3 keeps its answers (no layer question)", "Name?" not in questions)
check("going to a step: the later step 4 asks its questions again (view, dashed lines, labels)",
      "From which view do you want to see the device?" in questions
      and "Dashed lines from the electrodes to the coatings?" in questions and "Show labels?" in questions)
check("going to a step: then the tool goes on to the next open question", questions[-1] == "Image quality?")

# One way to move. A later step with answers: from step 2 straight to step 4 (step 2 keeps its answers).
yaml.safe_dump(data, open(stack_file, "w", encoding="utf8"), sort_keys=False)
front = ScriptedFront([("This design has saved answers", "render"), ("Image quality?", "GOTO 2"),
                       ("Which mask layer draws the device outline", "GOTO 4"), ("Image quality?", "STOP")])
ui.use(front)
saved_render_choices, step4_build_scene.render_choices = step4_build_scene.render_choices, lambda *a, **k: None
try:
    flow.run(mask)                                           # (no test images: render_choices does nothing)
except StopTest:
    pass
step4_build_scene.render_choices = saved_render_choices
questions = [q for q, _ in front.asked]
check("go to a later step: from step 2 to step 4; step 2 keeps its answers, step 4 asks again",
      sum(q.startswith("Which mask layer draws the device outline") for q in questions) == 1
      and "Which part of the device do you want to show?" in questions and "Name?" not in questions
      and answers.read_stack(stack_file).get("outline layer") == "OUTLINE")


class FormScript(ScriptedFront):
    """The window: forms, a click on a step; the forms give their answers back with no change."""
    SHOWS_FORMS = True

    def __init__(self, script):
        super().__init__(script)
        self.forms, self.answered, self.menus = [], [], []

    def ask_choice(self, question, help_text, options, default, details, side):
        self.menus.append(list(options))
        return super().ask_choice(question, help_text, options, default, details, side)

    def steps_with_answers(self, steps):
        self.answered.append(list(steps))

    def edit_stack(self, layers, make_questions, problems, open_layer=None):
        self.forms.append("stack")
        return [{k: v for k, v in layer.items() if k != "has a layer on top"} for layer in layers]

    def ask_page(self, help_text, questions, values):
        self.forms.append("page")
        return {q.key: values.get(q.key, q.initial(values)) for q in questions}


# The window: a click on step 3 at the start opens the stack form with the saved answers.
# Then the questions of step 4 come again (old answers = defaults): the page form, the view, the dashed lines.
yaml.safe_dump(data, open(stack_file, "w", encoding="utf8"), sort_keys=False)
front = FormScript([("This design has saved answers", "GOTO 3"), ("Image quality?", "STOP")])
ui.use(front)
step4_build_scene.render_choices = lambda *a, **k: None
try:
    flow.run(mask)
except StopTest:
    pass
step4_build_scene.render_choices = saved_render_choices
questions = [q for q, _ in front.asked]
check("window start menu: it has 'Change some answers'; it knows the steps with answers",
      "change" in front.menus[0] and [1, 2, 3, 4] in front.answered)
check("one way to move: a click on step 3 at the start opens the stack form; the answers stay the same",
      front.forms[:1] == ["stack"] and answers.read_stack(stack_file).get("layer 4 openings") ==
      "OPENINGS_ELECTRODES, OPENINGS_PADS")
check("one way to move: after the stack form, step 4 asks again (page form, view, dashed lines)",
      front.forms == ["stack", "page"] and "From which view do you want to see the device?" in questions
      and "Dashed lines from the electrodes to the coatings?" in questions)
check("one way to move: the old view answer is the default of the view question",
      [d for q, d in front.asked if q.startswith("From which view")] == ["1"])

# The window: "Change some answers", then step 3: the same as a click on step 3. Back from "Which step?": the menu.
yaml.safe_dump(data, open(stack_file, "w", encoding="utf8"), sort_keys=False)
front = FormScript([("This design has saved answers", "change"), ("Which step do you want", "BACK"),
                    ("This design has saved answers", "change"), ("Which step do you want", "3"),
                    ("Image quality?", "STOP")])
ui.use(front)
step4_build_scene.render_choices = lambda *a, **k: None
try:
    flow.run(mask)
except StopTest:
    pass
step4_build_scene.render_choices = saved_render_choices
questions = [q for q, _ in front.asked]
check("window 'Change some answers': Back from 'Which step?' shows the menu again; the steps 2, 3, 4 are options",
      questions[:3] == ["This design has saved answers. What do you want to do?", "Which step do you want to change?",
                        "This design has saved answers. What do you want to do?"]
      and front.menus[1] == ["2", "3", "4"])
check("window 'Change some answers', step 3: stack form, then all the step 4 questions; the answers stay the same",
      front.forms == ["stack", "page"] and "Dashed lines from the electrodes to the coatings?" in questions
      and answers.read_stack(stack_file).get("layer 4 openings") == "OPENINGS_ELECTRODES, OPENINGS_PADS")

# The window: a click on step 3 at "Image quality?" (the user selected "Render again"), Next on the stack form:
# the questions of step 4 come again, not straight the render.
yaml.safe_dump(data, open(stack_file, "w", encoding="utf8"), sort_keys=False)
front = FormScript([("This design has saved answers", "render"), ("Image quality?", "GOTO 3"),
                    ("Image quality?", "STOP")])
ui.use(front)
step4_build_scene.render_choices = lambda *a, **k: None
try:
    flow.run(mask)
except StopTest:
    pass
step4_build_scene.render_choices = saved_render_choices
questions = [q for q, _ in front.asked]
check("go to step 3 from 'Image quality?': stack form, then all the step 4 questions, then 'Image quality?'",
      front.forms == ["stack", "page"] and questions[-4:] == [
          "From which view do you want to see the device?",
          "Dashed lines from the electrodes to the coatings?", "Show labels?", "Image quality?"])
check("go to step 3: the answers of step 4 stay the same when the user keeps the defaults",
      answers.read_stack(stack_file).get("render camera turn and height") == "32, 11"
      and answers.read_stack(stack_file).get("render guide lines") == "all")

# A stop during a change (the window closes, Ctrl+C): the answers that "change one part" removed stay in the file.
yaml.safe_dump(data, open(stack_file, "w", encoding="utf8"), sort_keys=False)
ui.use(ScriptedFront([("This design has saved answers", "change"), ("Which part do you want", "view"),
                      ("Which part of the device", "STOP")]))
try:
    flow.run(mask)
except StopTest:
    pass
saved = answers.read_stack(stack_file)
check("stop during a change: the removed answers stay in stack.yaml",
      saved.get("render view") == "electrodes" and saved.get("render camera turn and height") == "32, 11"
      and saved.get("render labels") == "yes")
shutil.rmtree(folder, ignore_errors=True)
flow.PROJECTS, step4_build_scene.find_blender = saved_globals

# ── the results of a run: a new run never uses the results of an old run ──
from backend import run_cache

made = []
run_cache.clear()
run_cache.get("mask file", "a.dxf", lambda: made.append(1) or "shapes")
run_cache.get("mask file", "a.dxf", lambda: made.append(1) or "shapes")
check("run cache: one run makes a result one time", made == [1])
with tempfile.TemporaryDirectory() as temp:                  # flow.run() clears the cache at its start
    flow.PROJECTS = temp
    ui.use(ScriptedFront([("Which mask file", "STOP")]))
    try:
        flow.run()
    except StopTest:
        pass
    flow.PROJECTS = saved_globals[0]
check("run cache: a new run starts with no kept results (an edited mask file is read again)",
      not run_cache.has("mask file", "a.dxf") and run_cache.get("mask file", "a.dxf", lambda: "new") == "new")

failures = 0
for name, ok in RESULTS:
    failures += not ok
    print(f"{'PASS' if ok else 'FAIL'}  {name}")
print(f"\n{len(RESULTS) - failures} of {len(RESULTS)} tests pass.")
sys.exit(1 if failures else 0)
