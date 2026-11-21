"""
Step 1: read the mask file (DXF or GDS), find its unit and show its layers.

  1. Read all the shapes of the file, layer by layer.
     - DXF: the layers have names. A DXF file does not always give its unit.
     - GDS: the layers have numbers, written "layer/datatype" (example: "1/0"). A GDS file always gives its unit.
  2. Find the drawing unit. If the file does not give it, ask the user.
  3. Change all the values to mm. (All the next steps use mm.)
  4. Show one row for each layer and save one image of each layer.

A "closed shape" is a line that ends at its start point. Only closed shapes can become solid layers.
All the shapes of a GDS file are closed.
A GDS file has no layer names. The user gives each GDS layer a name one time; stack.yaml keeps the names.
"""
import json
import os
import re

import ezdxf
from ezdxf import disassemble, path
import matplotlib
matplotlib.use("Agg")                      # write image files only, open no window
import matplotlib.pyplot as plt
from matplotlib.collections import LineCollection, PatchCollection
from matplotlib.patches import Polygon

from backend import answers, run_cache, ui
from backend.answers import answer


# Mask designs use nm, µm, mm or cm. The tool uses only these units.
# DXF unit codes (header variable $INSUNITS) -> our unit names. A DXF file with another unit code (example: metre or
# inch, often a default value of the drawing program) counts as a file with no unit: the tool asks for the unit.
DXF_UNITS = {12: "nm", 13: "um", 4: "mm", 5: "cm"}
# size of one unit in mm
UNIT_IN_MM = {"nm": 1e-6, "um": 0.001, "mm": 1.0, "cm": 10.0}


GDS_ENDINGS = (".gds", ".gds2", ".gdsii")


def read_shapes(mask_file):
    """Read a DXF or a GDS file. Return the unit and the shapes of each layer (see read_dxf)."""
    if mask_file.lower().endswith(GDS_ENDINGS):
        return read_gds(mask_file)
    return read_dxf(mask_file)


def read_gds(gds_file):
    """Read a GDS file. Return the unit of the file ("um", "nm" or "mm") and the shapes of each layer.

    A GDS file gives its unit in metres (1e-6 = µm). A unit that is not nm, µm or mm is changed to mm here.
    The shapes inside cells and arrays (copies of one drawing) are opened into their shapes.
    A GDS file has no layer names: the layer name is "layer/datatype" (example: "1/0"), sorted by number.

    GDS writers cut a polygon with many points into pieces (KLayout above 8000 points, other tools above 199).
    The tool joins the pieces that touch, so that one device outline stays one shape (see join_pieces)."""
    import gdstk
    library = gdstk.read_gds(gds_file)
    unit = next((name for name, metres in (("nm", 1e-9), ("um", 1e-6), ("mm", 1e-3))
                 if abs(library.unit - metres) < 1e-3 * metres), None)
    scale = 1.0 if unit else library.unit * 1000      # other units: change the points to mm
    pieces = {}
    for cell in library.top_level():
        for polygon in cell.get_polygons(apply_repetitions=True, include_paths=True):
            name = f"{polygon.layer}/{polygon.datatype}"
            pieces.setdefault(name, []).append([(float(x) * scale, float(y) * scale) for x, y in polygon.points])
    order = sorted(pieces, key=lambda name: tuple(int(n) for n in name.split("/")))
    return unit or "mm", {name: {"closed": join_pieces(pieces[name]), "open": []} for name in order}


def join_pieces(rings):
    """Join the polygons of one layer that touch or overlap. Return the outer line and the hole lines of each
    joined shape, as closed shapes. (A shape inside another shape of the same layer is a hole: see step 4.)"""
    from shapely.geometry import Polygon as ShapelyPolygon
    from shapely.ops import unary_union
    joined = unary_union([ShapelyPolygon(r).buffer(0) for r in rings if len(r) >= 3])
    out = []
    for part in getattr(joined, "geoms", [joined]):
        if part.is_empty or part.geom_type != "Polygon":
            continue
        out.append(list(part.exterior.coords))
        out += [list(hole.coords) for hole in part.interiors]
    return out


def read_dxf(dxf_file):
    """Read a DXF file. Return the unit ("um", "mm" ... or None) and the shapes of each layer.

    layers = {layer name: {"closed": [shape, ...], "open": [shape, ...]}}, shape = list of (x, y) points.
    Blocks (copies of one drawing) are opened into their shapes.
    """
    doc = ezdxf.readfile(dxf_file)
    unit = DXF_UNITS.get(doc.header.get("$INSUNITS", 0))     # None when the DXF gives no unit

    outlines = []                                         # (layer name, outline path)
    for entity in disassemble.recursive_decompose(doc.modelspace()):
        if entity.dxftype() in ("TEXT", "MTEXT", "DIMENSION", "POINT"):
            continue                        # text and points have no area
        try:
            outlines.append((entity.dxf.layer, path.make_path(entity)))
        except TypeError:
            continue                        # this type of entity has no outline
    curve_tolerance, end_tolerance = dxf_tolerances([outline for _, outline in outlines])

    layers = {}
    for name, outline in outlines:
        points = [(p.x, p.y) for p in outline.flattening(distance=curve_tolerance)]
        if len(points) < 2:
            continue
        is_closed = len(points) > 3 and abs(points[0][0] - points[-1][0]) < end_tolerance \
            and abs(points[0][1] - points[-1][1]) < end_tolerance
        layer = layers.setdefault(name, {"closed": [], "open": []})
        layer["closed" if is_closed else "open"].append(points)
    return unit, layers


def dxf_tolerances(outlines):
    """The tolerances for reading a DXF file, from the size of the drawing (not from its unit), so that the same
    design gives the same shapes in µm, nm or mm:
      - curve tolerance: the largest distance from a curve (circle, arc, spline) to its line segments;
      - end tolerance:   the largest distance between the two ends of a closed line."""
    if not outlines:
        return 1e-3, 1e-6
    extents = path.bbox(outlines)
    size = max(extents.size.x, extents.size.y) or 1.0
    return size * 1e-5, size * 1e-7


def without_commas(layers):
    """A DXF layer name can contain a comma, but the answers keep lists of mask layers as "A, B". So a comma in a
    mask layer name changes to ";" (example: "OPEN, ELECTRODES" -> "OPEN; ELECTRODES"), with a note."""
    renamed = {name: name.replace(",", ";") for name in layers if "," in name}
    if renamed:
        ui.note("Comma in mask layer name changed to ';': " + "   ".join(f"{a} -> {b}" for a, b in renamed.items()))
    return {renamed.get(name, name): shapes for name, shapes in layers.items()}


def size_of(shapes):
    """Return (width, height) of the box around all the shapes."""
    xs = [x for shape in shapes for x, _ in shape]
    ys = [y for shape in shapes for _, y in shape]
    return max(xs) - min(xs), max(ys) - min(ys)


def ask_unit(layers):
    """Ask for the drawing unit (nm, µm, mm or cm). Give a likely unit as the default answer."""
    width, height = size_of([s for shapes in layers.values() for s in shapes["closed"] + shapes["open"]])
    largest = max(width, height)
    # A wafer or an implant is between 1 mm and 200 mm: 1 000 to 200 000 in µm, more than 1 000 000 in nm.
    likely = "nm" if largest > 1e6 else ("um" if largest > 1000 else "mm")
    shown = {"nm": "nm", "um": "µm", "mm": "mm"}[likely]
    ui.note(f"File gives no unit. Drawing is {largest:,.0f} units wide: unit likely {shown}.")
    return ui.ask_choice(
        "Which unit does the drawing use?", "",
        {"nm": "nm (nanometre)", "um": "µm (micrometre)", "mm": "mm (millimetre)", "cm": "cm (centimetre)"},
        default=answers.PREVIOUS.get("unit", likely))


def to_mm(layers, unit):
    """Change all the points from the drawing unit to mm."""
    k = UNIT_IN_MM[unit]
    return {name: {kind: [[(x * k, y * k) for x, y in s] for s in shapes[kind]] for kind in shapes}
            for name, shapes in layers.items()}


def print_layers(layers):
    """Show one row for each layer (sizes in mm). Open lines show in red: the render cannot use them."""
    rows = []
    for number, (name, shapes) in enumerate(layers.items(), start=1):
        width, height = size_of(shapes["closed"] + shapes["open"])
        n_open = len(shapes["open"])
        rows.append([number, name, len(shapes["closed"]), ui.alert(str(n_open)) if n_open else "0",
                     f"{width:.3g} x {height:.3g}"])
    ui.show_table(["#", "mask layer", "closed", "open", "size (mm)"], rows, title=f"Your file has {len(layers)} layers")
    ui.note("closed = closed shapes (can become solid layers).  open = open lines (render cannot use them).")


def save_layer_images(layers, folder, title_start="Layer"):
    """Save one image for each layer. The layer shows in blue; the other layers show in light grey.
    If this run made the same images already (the user went back), keep them: this is fast."""
    key = (os.path.abspath(folder), title_start,
           tuple((name, len(s["closed"]), len(s["open"]), round(sum(p[0] + p[1] for r in s["closed"][:3] for p in r), 6))
                 for name, s in layers.items()))
    if run_cache.has("layer images", key) and os.path.isdir(folder):
        ui.show_path("Layer images:", folder)
        return
    os.makedirs(folder, exist_ok=True)
    all_points = [p for shapes in layers.values() for s in shapes["closed"] + shapes["open"] for p in s]
    xs, ys = [p[0] for p in all_points], [p[1] for p in all_points]
    width, height = max(xs) - min(xs), max(ys) - min(ys)
    scale = 8 / max(width, height)                       # the longer side of the image = 8 inch
    fig_size = (max(width * scale, 2.5), max(height * scale, 2.5))

    # One figure for all the images. Each layer has one light grey collection (for position), made one time. For
    # each image, the grey of this layer is hidden, its shapes go on top (blue, open lines red), the image is saved,
    # and these shapes go again. (Before: each image drew all the other layers again, line by line: slow on a wafer.)
    fig, ax = plt.subplots(figsize=fig_size)
    grey = {name: ax.add_collection(LineCollection(shapes["closed"] + shapes["open"], colors="0.85", linewidths=0.3))
            for name, shapes in layers.items()}
    ax.set_xlim(min(xs), max(xs))
    ax.set_ylim(min(ys), max(ys))
    ax.set_aspect("equal")
    ax.set_xlabel("mm")
    for number, (name, shapes) in enumerate(layers.items(), start=1):
        grey[name].set_visible(False)
        on_top = []
        if shapes["closed"]:                                # this layer: filled shapes
            on_top.append(ax.add_collection(PatchCollection([Polygon(s, closed=True) for s in shapes["closed"]],
                                                            facecolor="tab:blue", edgecolor="navy", linewidth=0.3)))
        if shapes["open"]:                                  # this layer: open lines in red
            on_top.append(ax.add_collection(LineCollection(shapes["open"], colors="red", linewidths=0.6)))
        ax.set_title(f"{title_start} {number}: {name}\n{len(shapes['closed'])} closed, {len(shapes['open'])} open",
                     fontsize=9)
        safe_name = "".join(c if c.isalnum() or c in "-_" else "_" for c in name)
        fig.savefig(os.path.join(folder, f"{number:02d}_{safe_name}.png"), dpi=150, bbox_inches="tight")
        for artist in on_top:
            artist.remove()
        grey[name].set_visible(True)
    plt.close(fig)
    run_cache.add("layer images", key)
    ui.show_path("Layer images:", folder)


def run(dxf_file, stack, project_folder):
    """Do step 1. Return the layers in mm. Write the unit into the stack (a dictionary)."""
    ui.header(1)
    def read():
        with ui.working(f"Reading {os.path.basename(dxf_file)} ... (large file: up to 30 s)"):
            return read_shapes(dxf_file)
    unit, layers = run_cache.get("mask file", dxf_file, read)   # read one time in a run, also when the user goes back
    if not layers:
        raise answers.Stop("File has no shapes. Check that it is the correct file.")

    if unit:
        ui.note(f"Unit from file: {'µm' if unit == 'um' else unit}.")
        stack["unit"] = unit
    else:
        answer(stack, "unit", lambda: ask_unit(layers), is_valid=lambda u: u in UNIT_IN_MM)

    layers = without_commas(to_mm(layers, stack["unit"]))
    if dxf_file.lower().endswith(GDS_ENDINGS):          # a GDS file has only layer numbers: the user names them
        names = json.loads(answer(stack, "layer names", lambda: json.dumps(
            ask_layer_names(layers, dxf_file, project_folder)), is_valid=lambda text: valid_names(text, layers)))
        layers = {names.get(number, number): shapes for number, shapes in layers.items()}
    print_layers(layers)
    with ui.working("Saving layer images ..."):
        save_layer_images(layers, os.path.join(project_folder, "1_all_layers"))
    return layers


# ───────────────────────────────────────────────────────── names of GDS layers ──

def valid_names(text, layers):
    """True if text is a saved set of names ({"4/0": "outline", ...}) for these layers, with no name two times."""
    try:
        names = json.loads(text)
    except ValueError:
        return False
    final = [names.get(number, number) for number in layers]
    return isinstance(names, dict) and len(set(final)) == len(final)


def klayout_names(gds_file):
    """Read the layer names from a KLayout layer file (.lyp) with the same name as the GDS file, if it exists.
    Return {"4/0": "outline", ...}, or an empty dictionary."""
    lyp = os.path.splitext(gds_file)[0] + ".lyp"
    if not os.path.exists(lyp):
        return {}
    import xml.etree.ElementTree as ElementTree
    names = {}
    for item in ElementTree.parse(lyp).getroot().iter("properties"):
        name, source = item.findtext("name") or "", item.findtext("source") or ""
        match = re.match(r"\s*(\d+)/(\d+)", source)
        if match and name.strip():
            names[f"{match.group(1)}/{match.group(2)}"] = re.sub(r"\s*\d+/\d+(@\d+)?\s*$", "", name).strip() or name
    return names


def save_layer_overview(layers, file):
    """Save one image with all the layers next to each other: each one in blue, with its number and its shapes."""
    columns = min(4, len(layers))
    rows = (len(layers) + columns - 1) // columns
    fig, axes = plt.subplots(rows, columns, figsize=(4 * columns, 4 * rows), squeeze=False)
    all_points = [p for shapes in layers.values() for s in shapes["closed"] for p in s]
    xs, ys = [p[0] for p in all_points], [p[1] for p in all_points]
    for ax, (name, shapes) in zip(axes.flat, layers.items()):
        for s in shapes["closed"]:
            ax.add_patch(Polygon(s, closed=True, facecolor="tab:blue", edgecolor="navy", linewidth=0.2))
        ax.set_xlim(min(xs), max(xs))
        ax.set_ylim(min(ys), max(ys))
        ax.set_aspect("equal")
        ax.set_xticks([])
        ax.set_yticks([])
        n = len(shapes["closed"])
        ax.set_title(f"{name}   ({n} shape{'s' if n != 1 else ''})", fontsize=12, fontweight="bold")
    for ax in list(axes.flat)[len(layers):]:
        ax.axis("off")
    fig.tight_layout()
    fig.savefig(file, dpi=110)
    plt.close(fig)


def ask_layer_names(layers, gds_file, project_folder):
    """Ask a name for each GDS layer. Show an overview image of all the layers first. Return {number: name}."""
    overview = os.path.join(project_folder, "1_layer_overview.png")
    os.makedirs(project_folder, exist_ok=True)
    with ui.working("Making overview of all layers ..."):
        save_layer_overview(layers, overview)
    ui.note("GDS file: layer numbers, no names (4/0 = layer 4, datatype 0).\n"
            "Name each layer for clear questions. Default answer keeps the number.")
    ui.show_path("All layers:", overview, open_now=True)
    defaults = klayout_names(gds_file)
    if answers.PREVIOUS.get("layer names"):                 # going back: the names of the user are the defaults
        defaults.update(json.loads(answers.PREVIOUS["layer names"]))
    if defaults:
        ui.note(f"Names from KLayout file {os.path.splitext(os.path.basename(gds_file))[0]}.lyp.")
    names = {}
    for number, shapes in layers.items():
        n = len(shapes["closed"])
        width, height = size_of(shapes["closed"])
        taken = set(names.values())
        name = ui.ask(f"Name of layer {number}?", f"{n} shape{'s' if n != 1 else ''}, {width:.3g} x {height:.3g} mm",
                      defaults.get(number, number),
                      lambda text: "No comma in a name (lists of mask layers use commas)." if "," in text else
                      (f"Name {text} already used. Type another name." if text in taken else None))
        names[number] = name
    return names
