"""
Step 2: select the device to render.

  1. Ask which layer draws the device outline. (The outline = the shape of one whole device.)
  2. If the outline layer has more than one shape, the DXF holds many devices (a full wafer).
     Save an image with a number on each device, and ask for the device number.
  3. Keep the shapes of this device. Cut the shapes that cross the outline (example: plating bus lines).
     Move the device so that its lower-left corner is at (0, 0).
  4. Print the layers of the device and save one image of each layer.
"""
import os

import matplotlib
matplotlib.use("Agg")                      # write image files only, open no window
import matplotlib.pyplot as plt
from matplotlib.patches import Polygon as PolygonPatch
from shapely.geometry import Polygon
from shapely.prepared import prep

from backend import answers, run_cache, ui
from backend.answers import answer, split_layers
from backend.step1_read_mask import save_layer_images


def sort_devices(outlines):
    """Sort the device outlines in reading order: rows from top to bottom, each row from left to right."""
    height = sorted(p.bounds[3] - p.bounds[1] for p in outlines)[len(outlines) // 2]   # typical height
    row = lambda p: round(-p.centroid.y / (height / 2))        # devices in one row get the same number
    return sorted(outlines, key=lambda p: (row(p), p.centroid.x))


def save_device_map(outlines, file):
    """Save an image of all the device outlines with a number on each one (only one time in a run)."""
    key = (os.path.abspath(file), len(outlines), round(sum(p.area for p in outlines), 9))
    if run_cache.has("device map", key) and os.path.exists(file):
        return
    run_cache.add("device map", key)
    fig, ax = plt.subplots(figsize=(9, 9))
    for number, p in enumerate(outlines, start=1):
        ax.add_patch(PolygonPatch(list(p.exterior.coords), facecolor="0.92", edgecolor="0.3", linewidth=0.4))
        ax.text(p.centroid.x, p.centroid.y, str(number), ha="center", va="center", fontsize=8,
                fontweight="bold", color="tab:red")
    ax.autoscale_view()
    ax.set_aspect("equal")
    ax.set_xlabel("mm")
    ax.set_title("Device numbers")
    fig.savefig(file, dpi=150, bbox_inches="tight")
    plt.close(fig)


def shapes_inside(layers, device):
    """Keep the closed shapes of the device. Return (layers of the device, {layer: number of shapes cut}).

    - A shape inside the outline stays as it is. A small margin (1 % of the device width) accepts shapes that touch
      the outline.
    - A shape that crosses the outline is cut at the outline. Example: tracks that go to a plating bus line, or to a
      connector outside the cut outline. (Before, the tool removed these shapes, and the image had missing tracks.)
    - A shape that covers the full device (example: the wafer, or a layer drawn over the full wafer) is cut to the
      device shape, with no warning: it is not a cut track.
    - A shape fully outside the outline goes.
    Then move all shapes so that the lower-left corner of the device is at (0, 0).
    """
    x0, y0, x1, y1 = device.bounds
    margin = 0.01 * min(x1 - x0, y1 - y0)
    area = prep(device.buffer(margin))
    shift = lambda ring: [(x - x0, y - y0) for x, y in ring]
    inside, cut = {}, {}
    for name, shapes in layers.items():
        kept = []
        for s in shapes["closed"]:
            shape = Polygon(s)
            if area.contains(shape):
                kept.append(shift(s))
                continue
            if not area.intersects(shape):
                continue
            shape = shape if shape.is_valid else shape.buffer(0)
            part = shape.intersection(device)
            pieces = [g for g in getattr(part, "geoms", [part]) if g.geom_type == "Polygon" and g.area > 0]
            for piece in pieces:                          # the outer line and the hole lines, as closed shapes
                kept += [shift(piece.exterior.coords)] + [shift(hole.coords) for hole in piece.interiors]
            if pieces and not shape.contains(device):
                cut[name] = cut.get(name, 0) + 1
        if kept:
            inside[name] = {"closed": kept, "open": []}
    return inside, cut


def run(layers, stack, project_folder):
    """Do step 2. Return the layers of one device (in mm, lower-left corner at 0, 0)."""
    ui.header(2)
    ui.note("Folder 1_all_layers: one image per mask layer.")
    counts = {name: len(shapes["closed"]) for name, shapes in layers.items()}
    while True:                                           # a layer with no closed shapes: ask again
        outline_layer = answer(stack, "outline layer", lambda: ui.ask_layer(
            list(layers), "Which mask layer draws the device outline?", counts=counts,
            default=answers.PREVIOUS.get("outline layer"), help_text="outline = device shape after cutting"),
            is_valid=lambda name: name in layers)
        shapes = [p for p in (Polygon(s).buffer(0) for s in layers[outline_layer]["closed"]) if p.area > 0]
        # A shape inside another shape of the outline layer is a hole in that device (example: a suture hole), not a
        # device. buffer(0) repairs small drawing errors.
        outlines = sort_devices([p for p in shapes if not any(
            q.area > p.area and q.contains(p.representative_point()) for q in shapes)])
        if outlines:
            break
        ui.warn(f"Layer {outline_layer} has no closed shapes. Select another outline layer.")
        answers.forget(stack, "outline layer")

    if len(outlines) == 1:
        number = 1
        ui.note("File holds one device.")
    else:
        with ui.working("Saving device numbers image ..."):
            save_device_map(outlines, os.path.join(project_folder, "2_device_numbers.png"))
        ui.show_path("Device numbers:", os.path.join(project_folder, "2_device_numbers.png"))
        number = int(answer(stack, "device number", lambda: ui.ask_number(
            f"File holds {len(outlines)} devices. Which device do you want to render?",
            "see image of device numbers", 1, len(outlines), answers.PREVIOUS.get("device number")),
            is_valid=lambda n: n.isdigit() and 1 <= int(n) <= len(outlines)))
    stack["device number"] = str(number)

    device = outlines[number - 1]
    device_layers, cut = shapes_inside(layers, device)
    if cut:
        ui.warn("Shapes cut at device outline (they cross it): "
                + ", ".join(f"{name} {n}" for name, n in cut.items()) + ".\nCheck these layers in the image.")
    x0, y0, x1, y1 = device.bounds
    rows = []
    for name in layers:
        count = len(device_layers.get(name, {}).get("closed", []))
        rows.append([name, count] if count else [ui.faded(name), ui.faded("not in this device")])
    ui.show_table(["mask layer", "shapes"], rows, title=f"Device {number}: {x1 - x0:.3g} mm x {y1 - y0:.3g} mm")
    with ui.working("Saving device layer images ..."):
        save_layer_images(device_layers, os.path.join(project_folder, "3_device_layers"), "Device layer")

    # Through holes: holes through the whole device (all the layers), for example suture holes.
    # One list: "no through holes" (ticked at the start) or the mask layers of the holes.
    names = list(device_layers)
    ui.note("Folder 3_device_layers: one image per mask layer of device.\n"
            "Through hole = hole through all layers (example: suture hole).")
    answer(stack, "through holes", lambda: ui.ask_layers(
        names, "Which mask layers draw the through holes?",
        counts={name: len(shapes["closed"]) for name, shapes in device_layers.items()},
        default=answers.PREVIOUS.get("through holes", "none"), none_text="no through holes"),
        is_valid=lambda text: text == "none" or (bool(split_layers(text)) and all(n in names for n in split_layers(text))))
    return device_layers
