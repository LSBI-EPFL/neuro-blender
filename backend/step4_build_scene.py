"""
Step 4: prepare the 3D scene and render it with Blender.

  1. Ask which part of the device to show (the electrodes, or the whole device), the cleave angle, the space
     between the layers, the view, and the image quality (a quick preview, or the final image).
  2. Turn the device so that its long side is along y and the electrodes are at the far end (+y).
  3. Make the 2D shape of each layer: its DXF shape, minus its openings.
  4. Calculate the drawn thickness of each layer, and how the cleaved layers bend.
     Real layers are too thin to see (3 µm on a 3 mm device), so the image shows them thicker.
     The encapsulation layer on the tracks fills the space around the tracks, down to the layer under them,
     as in the real device.
  5. Write all of this into 5_scene.json, and run Blender with backend/blender_render.py.

Blender writes 5_render.png (the device on a transparent background) and 5_render_points.json
(the image position of each layer, for the labels of step 5).
"""
import copy
import json
import math
import os

from shapely import affinity
from shapely.geometry import Polygon, box
from shapely.ops import polygonize, unary_union

import matplotlib
matplotlib.use("Agg")                      # write image files only, open no window
import matplotlib.image as mpimg
import matplotlib.pyplot as plt

from backend import answers, blender_protocol, run_cache, ui
from backend.answers import answer, shown, split_layers, thickness_in_mm
from backend.blender_runner import check_blender_version, find_blender, run_blender
from backend.questions import Question, answer_page

# Look of the exploded view. Lengths are fractions of the device width, angles are in degrees.
LOOK = dict(
    thickest_layer=0.035,    # drawn thickness of the thickest layer
    thinnest_layer=0.009,    # drawn thickness of the thinnest layer
    tallest_to_feature=0.35, # limit: the thickest layer is at most 0.35 x the typical width of the device features
    cleave_angle=9.0,        # default answer: each cleaved layer opens 9° more than the layer next to it
    space_flat=30,           # default answer with no cleave: space between the layers = 30 image units (see image_units)
    coating_distance=20,     # default answer: distance from the top layer to the first coating (image units)
    coating_gap=35,          # distance between two coating materials (image units): each material shows separately
    small_electrode_scale=2.0,
    round_edges=0.5,         # radius of the rounded edges (the fillet) = 0.5 x the drawn thickness: a fully round edge
    round_to_width=0.2,      # limit: the radius is at most 0.2 x the width of the narrowest shape of the object
)


# ───────────────────────────────────────────────────────── 2D shapes ──

def parts(geometry):
    """Return the polygons of a shapely geometry as a list."""
    if geometry.is_empty:
        return []
    if isinstance(geometry, Polygon):
        return [geometry]
    return [g for g in getattr(geometry, "geoms", []) if isinstance(g, Polygon) and not g.is_empty]


def rings_to_polygons(rings):
    """Make polygons from the closed shapes of one mask layer.

    A DXF file has no holes: a shape inside another shape of the same layer is a hole.
    So: a shape inside 0, 2, 4... other shapes is solid; a shape inside 1, 3... other shapes is a hole.
    """
    shapes = [p for r in rings for p in parts(Polygon(r).buffer(0))]
    shapes.sort(key=lambda p: -p.area)
    solids, holes_of = [], {}
    for i, p in enumerate(shapes):
        point = p.representative_point()
        containers = [j for j in range(i) if shapes[j].contains(point)]
        if len(containers) % 2 == 0:
            solids.append(i)
        else:
            holes_of.setdefault(containers[-1], []).append(p)
    result = []
    for i in solids:
        result += parts(shapes[i].difference(unary_union(holes_of.get(i, []))))
    return result


def precision(width):
    """The tolerances of the scene, from the width of the device (mm), not fixed in mm, so that a small design and a
    large design keep the same detail. Return (simplify, decimals):
      simplify: shapes lose details smaller than this (mm);
      decimals: the coordinates in the scene file keep this number of decimals (at least 5).
    Example: width 1.2 mm -> simplify 0.24 µm, 6 decimals (1 nm)."""
    return width * 2e-4, max(5, math.ceil(-math.log10(width * 1e-6)))


def to_json(polygons, simplify, decimals):
    """Polygons -> lists of points for the JSON file (details smaller than `simplify` removed)."""
    out = []
    for p in polygons:
        p = p.simplify(simplify)
        if p.is_empty or not isinstance(p, Polygon):
            continue
        out.append(dict(exterior=[[round(x, decimals), round(y, decimals)] for x, y in p.exterior.coords[:-1]],
                        holes=[[[round(x, decimals), round(y, decimals)] for x, y in h.coords[:-1]]
                               for h in p.interiors]))
    return out


def equal_diameter(p):
    """Diameter of the circle with the same area as the polygon."""
    return 2 * math.sqrt(p.area / math.pi)


# ───────────────────────────────────────────────────────── orientation ──

def orient(device_layers, layers, outline_layer, electrode_layers=None):
    """Turn and move all the shapes: the electrodes at the top (+y), the lower-left corner at (0, 0).
    Return a function that changes one polygon.

    The turn is 0, 90, 180 or 270 degrees:
      1. The electrodes are away from the middle of the device (more than 10 % of its size): the turn that points
         the line from the middle to the electrodes most to +y. This also works for a round device (cuff, ring),
         which has no long side.
      2. Else (no electrodes, or electrodes in the middle): the long side along y, and the electrodes at the top."""
    outline = unary_union(rings_to_polygons(device_layers[outline_layer]["closed"]))
    x0, y0, x1, y1 = outline.bounds
    electrodes = electrode_shapes(device_layers, layers, electrode_layers=electrode_layers)
    angle = None
    if electrodes:
        middle, sites = outline.centroid, unary_union(electrodes).centroid
        dx, dy = sites.x - middle.x, sites.y - middle.y
        if math.hypot(dx, dy) > 0.1 * max(x1 - x0, y1 - y0):
            # y after a turn by a degrees (counterclockwise): dx sin(a) + dy cos(a)
            angle = max((0, 90, 180, 270), key=lambda a: dx * math.sin(math.radians(a)) + dy * math.cos(math.radians(a)))
    if angle is None:
        angle = 90 if (x1 - x0) > (y1 - y0) else 0        # long side along x: turn 90°
        turned = affinity.rotate(outline, angle, origin=(0, 0))
        if electrodes:
            low, high = turned.bounds[1], turned.bounds[3]
            sites = unary_union([affinity.rotate(p, angle, origin=(0, 0)) for p in electrodes]).centroid
            if sites.y < (low + high) / 2:
                angle += 180                              # electrodes at the low end: turn 180° more
    turned = affinity.rotate(outline, angle, origin=(0, 0))
    dx, dy = -turned.bounds[0], -turned.bounds[1]
    return lambda p: affinity.translate(affinity.rotate(p, angle, origin=(0, 0)), dx, dy)


def electrode_shapes(device_layers, layers, change=lambda p: p, electrode_layers=None):
    """The electrode sites, in this order of preference:
      1. the shapes of the coating layers (a coating is on the electrodes only);
      2. the mask layers that the user selected as electrode openings (electrode_layers, a list of names);
      3. all the openings of the top encapsulation layer. (These can include the contact pads.)"""
    shapes = [change(p) for layer in layers if layer["type"] == "electrode coating"
              for p in rings_to_polygons(device_layers[layer["shape"]]["closed"])]
    if shapes:
        return shapes
    if electrode_layers:
        return [change(p) for name in electrode_layers if name in device_layers
                for p in rings_to_polygons(device_layers[name]["closed"])]
    top_openings = [layer["openings"] for layer in layers
                    if layer["type"] == "encapsulation" and layer.get("openings", "none") != "none"]
    if top_openings:
        return [change(p) for name in split_layers(top_openings[-1])
                for p in rings_to_polygons(device_layers[name]["closed"])]
    return []


def openings_layers(layers):
    """All the mask layers that draw openings in the encapsulation layers, in the order of the stack (no repeats)."""
    names = []
    for layer in layers:
        if layer["type"] == "encapsulation":
            names += [n for n in split_layers(layer.get("openings", "none")) if n not in names]
    return names


# ───────────────────────────────────────────────────────── the scene ──

def drawn_thickness(layers, width):
    """Drawn thickness (mm) of each material: {id(material): thickness}.

    1. Each layer (the sum of its materials) gets a drawn thickness. The real layer thicknesses keep their order,
       on a log scale: a thin metal layer is never drawn thicker than a thick polymer layer.
    2. The materials of one layer share the drawn thickness of the layer, in proportion to their real thickness,
       but each one gets at least MIN_SHARE of it, so that a thin film (example: 25 nm Ti) stays visible.
    An electrode coating is different: each of its materials floats as a separate disc, so each material counts
    as one layer of its own."""
    groups = []                                           # the groups of materials that share one drawn thickness
    for layer in layers:
        if layer["type"] == "electrode coating":
            groups += [[m] for m in layer["materials"]]
        else:
            groups.append(layer["materials"])
    totals = [sum(thickness_in_mm(m["thickness"]) for m in group) for group in groups]
    low, high = math.log(min(totals)), math.log(max(totals))
    drawn = {}
    for group, total in zip(groups, totals):
        f = 0.5 if high == low else (math.log(total) - low) / (high - low)
        group_drawn = width * (LOOK["thinnest_layer"] + f * (LOOK["thickest_layer"] - LOOK["thinnest_layer"]))
        shares = shares_with_minimum([thickness_in_mm(m["thickness"]) for m in group], MIN_SHARE)
        for m, share in zip(group, shares):
            drawn[id(m)] = group_drawn * share
    return drawn


def shares_with_minimum(values, minimum):
    """Shares (sum = 1) in proportion to the values, but each share is at least `minimum`.
    Example: Ti 20 nm, Au 200 nm with minimum 0.2 -> Ti 0.2, Au 0.8 (in proportion: Ti 0.09, Au 0.91).
    The small values get the minimum; the other values share the rest in proportion."""
    if minimum * len(values) >= 1:
        return [1 / len(values)] * len(values)
    small = set()
    while True:
        rest = 1 - minimum * len(small)
        total = sum(v for i, v in enumerate(values) if i not in small)
        shares = [minimum if i in small else rest * v / total for i, v in enumerate(values)]
        new_small = {i for i, share in enumerate(shares) if i not in small and share < minimum}
        if not new_small:
            return shares
        small |= new_small


MIN_SHARE = 0.2     # the smallest part of a layer's drawn thickness that one material of the layer gets


def layer_label(layer):
    """The label text of a flat layer. One material: "3 µm" (or "PI · 3 µm" if the name is not the material).
    More materials: "Ti / Pt / Ti · 25 / 150 / 25 nm"."""
    materials = layer["materials"]
    if len(materials) == 1:
        m = materials[0]
        return shown(m["thickness"]) if m["name"] == layer["name"] else f"{m['name']} · {shown(m['thickness'])}"
    units = {m["thickness"].split()[1] for m in materials}
    names = " / ".join(m["name"] for m in materials)
    if len(units) == 1:
        numbers = " / ".join(m["thickness"].split()[0] for m in materials)
        return f"{names} · {numbers} {shown('0 ' + units.pop()).split()[1]}"
    return " / ".join(f"{m['name']} {shown(m['thickness'])}" for m in materials)


UNITS_OF_THICKEST = 10   # image units: the thickest layer in the image is 10 units thick


def image_unit(layers, drawn):
    """The size of one image unit (mm): the drawn thickness of the thickest layer / 10.
    A layer = the sum of its materials; a coating material floats alone, so it counts alone."""
    thickest = max(max(drawn[id(m)] for m in layer["materials"]) if layer["type"] == "electrode coating"
                   else sum(drawn[id(m)] for m in layer["materials"]) for layer in layers)
    return thickest / UNITS_OF_THICKEST


def thickness_in_image_units(layers):
    """The text that tells the drawn thickness of each layer in image units. Example:
    "Bottom PI 10, Tracks 3, Top PI 10, Electrode coating 2". The image units give the user a scale for the space
    between the layers: real thicknesses (nm, µm) are not useful, because the image is not to scale."""
    drawn = drawn_thickness(layers, 1.0)
    unit = image_unit(layers, drawn)
    parts = []
    for layer in layers:
        total = sum(drawn[id(m)] for m in layer["materials"])
        parts.append(f"{layer['name']} {max(1, round(total / unit))}")
    return ", ".join(parts)


def wrap_pieces(area, tracks, bottom, clearance, simplify):
    """The encapsulation layer on the tracks covers the tracks and touches the layer under them at their sides.
    So its bottom face is not flat: it goes down around the tracks.

    area      = the polygons of the encapsulation layer (its shape minus its openings);
    tracks    = [(polygons of one tracks layer, height of its top face)], from the bottom layer up;
    bottom    = the height of the bottom face of the tracks;
    clearance = a very small space around the tracks, so that no two faces are in one plane;
    simplify  = the simplify tolerance of the scene (see precision).
    Return the pieces of the bottom face: [(polygon, height of its bottom)]. Two pieces next to each other have
    the same border points, so that Blender can join them into one closed solid."""
    area = unary_union([p.simplify(simplify) for p in area])
    footprints = [(unary_union([p.simplify(simplify) for p in polygons]).buffer(clearance, join_style="mitre"), top)
                  for polygons, top in tracks]
    lines = unary_union([area.boundary] + [f.boundary for f, _ in footprints if not f.is_empty])
    pieces = []
    for face in polygonize(lines):                        # all the areas between the lines
        point = face.representative_point()
        if not area.contains(point):
            continue
        height = bottom
        for footprint, top in footprints:                 # above a track: the bottom is on the top of the track
            if footprint.contains(point):
                height = top
        pieces.append((face, height))
    return pieces


def pieces_to_json(pieces, decimals):
    """Pieces -> lists of points for the JSON file. No simplification: the border points must stay the same."""
    r = lambda value: round(value, decimals)
    return [dict(exterior=[[r(x), r(y)] for x, y in p.exterior.coords[:-1]],
                 holes=[[[r(x), r(y)] for x, y in h.coords[:-1]] for h in p.interiors], z=r(z))
            for p, z in pieces]


def main_shapes(polygons):
    """The shapes that count for a width: not the very small ones (below 1 % of the largest shape)."""
    largest = max((p.area for p in polygons), default=0)
    return [p for p in polygons if p.length and p.area >= 0.01 * largest]


def narrowest_width(polygons):
    """The width of the narrowest main shape (width = 2 x area / perimeter: for a long strip, its width)."""
    return min((2 * p.area / p.length for p in main_shapes(polygons)), default=float("inf"))


def edge_radius(polygons, thickness):
    """Radius of the rounded edges (the fillet) of one object: LOOK["round_edges"] x its drawn thickness, but at most
    LOOK["round_to_width"] x the width of its narrowest shape. So the rounded edges of the two sides of a shape never
    cross. LOOK["round_edges"] = 0 gives sharp edges."""
    main = main_shapes(polygons)
    radius = min(LOOK["round_edges"] * thickness, LOOK["round_to_width"] * narrowest_width(polygons))
    if not radius > 0 or radius == float("inf"):          # sharp edges, or nothing to measure
        return 0.0
    # A narrow neck in a wide shape: 2 x area / perimeter does not see it. Shrink each shape by the radius: if it
    # breaks into more parts, disappears, or two of its openings join (a narrow bridge between two openings, or
    # between an opening and the edge), a neck is narrower than two radii, and the bevels would cross. Then halve
    # the radius (at most 6 times).
    holes = lambda g: sum(len(q.interiors) for q in parts(g))
    for p in main:
        for _ in range(6):
            inner = p.buffer(-1.05 * radius)
            if not inner.is_empty and len(parts(inner)) <= len(parts(p)) and holes(inner) >= holes(p):
                break
            radius /= 2
    return radius


def without_slivers(polygons, radius):
    """Remove the parts of a layer that are narrower than its two rounded edges (2 x radius): they cannot have
    rounded edges, and the bevel of Blender makes broken shapes on them. Example: an opening that ends a little
    inside the device outline (two mask layers at a very small angle) leaves a thin strip along the edge.
    edge_radius() makes the radius small enough for the real necks and bridges, so only thin strips and spikes go."""
    if radius <= 0:
        return polygons
    out = []
    for p in polygons:
        kept = p.buffer(-radius, join_style=2).buffer(radius, join_style=2).intersection(p)
        out += [q for q in parts(kept) if 2 * q.area / q.length > 0.5 * radius]   # no thin rest of the cut
    return out


def bend_groups(layers):
    """Find how each encapsulation layer bends.

    Go out from the tracks (up for the layers above, down for the layers below). A cleaved layer starts a
    new group: it opens one cleave angle more than the group before it. A layer that is not cleaved stays
    bonded to the group next to it (with no group: it stays flat with the tracks).
    Return {layer index: (group number, side)}; group number 0 = flat. side = +1 above, -1 below.
    """
    track_rows = [i for i, layer in enumerate(layers) if layer["type"] == "tracks"]
    first, last = min(track_rows), max(track_rows)
    groups = {}
    for side, rows in ((+1, range(last + 1, len(layers))), (-1, range(first - 1, -1, -1))):
        group = 0
        for i in rows:
            if layers[i]["type"] != "encapsulation":
                continue
            if layers[i]["cleave"] == "yes":
                group += 1
            groups[i] = (group, side)
    return groups


def build_scene(device_layers, layers, stack, view, enlarge, cleave_angle, space, coating_distance=None):
    """Make the full scene description for Blender (a dictionary).
    cleave_angle: degrees between two cleaved layers next to each other (0 = all layers flat).
    space: the space between two layers, in image units (the thickest layer in the image = 10 units).
    coating_distance: the distance from the top layer to the first coating, in image units."""
    electrode_layers = split_layers(stack.get("render electrode openings", "none")) or None
    change = orient(device_layers, layers, stack["outline layer"], electrode_layers)
    shapes = lambda dxf_layer: [change(p) for p in rings_to_polygons(device_layers[dxf_layer]["closed"])]

    outline = unary_union(shapes(stack["outline layer"]))
    length = outline.bounds[3]
    sites = [change(p) for p in electrode_shapes(device_layers, layers, electrode_layers=electrode_layers)]
    notes = ["Not to scale: thicknesses and gaps drawn larger."]

    # Small electrodes drawn larger: the sites, the openings over them and the metal under them.
    small = []
    if enlarge == "yes" and sites:
        largest = max(equal_diameter(s) for s in sites)
        small = [s for s in sites if equal_diameter(s) < largest / 3]
        notes.append(f"Small electrodes drawn {LOOK['small_electrode_scale']:g}x larger.")

    def enlarged(polygons, add_metal_rim=False):
        out = []
        for p in polygons:
            site = next((s for s in small if s.intersects(p) and p.area < 4 * s.area), None)
            if site is None:
                out.append(p)
            else:
                out.append(affinity.scale(p, LOOK["small_electrode_scale"], LOOK["small_electrode_scale"],
                                          origin=site.centroid))
        if add_metal_rim:                                 # the metal disc under an enlarged site
            rims = [affinity.scale(s, LOOK["small_electrode_scale"], LOOK["small_electrode_scale"], origin="centroid")
                    for s in small]
            rims = [r.buffer(0.15 * equal_diameter(r)) for r in rims]
            out = parts(unary_union(out + rims))
        return out

    # The part of the device to show, and where the cleave starts (the hinge).
    if view == "electrodes" and sites:
        site_start = min(s.bounds[1] for s in sites)
        region_width = outline.intersection(box(-1e9, site_start, 1e9, length)).bounds
        width = region_width[2] - region_width[0]
        size = max(length - site_start, width)
        hinge = site_start - 0.25 * size
        crop_start = max(0.0, hinge - 0.5 * size)
    else:
        width = outline.bounds[2] - outline.bounds[0]
        hinge, crop_start = 0.3 * length, 0.0
    simplify, decimals = precision(width)
    crop = box(-1e9, crop_start, 1e9, length + 1)
    bend_length = 0.5 * (length - hinge)

    # Through holes (example: suture holes): they go through all the layers.
    through_holes = unary_union([p for name in split_layers(stack.get("through holes", "none")) for p in shapes(name)])

    drawn = drawn_thickness(layers, width)

    # Narrow features (example: a mesh of thin ribbons): the drawn layers must not be taller than the features
    # are wide. Typical feature width = 2 x area / perimeter of the device outline (a long strip: its width).
    shown_outline = outline.intersection(crop)
    feature_width = 2 * shown_outline.area / shown_outline.length if shown_outline.length else width
    limit = LOOK["tallest_to_feature"] * feature_width
    if max(drawn.values()) > limit:
        factor = limit / max(drawn.values())
        drawn = {key: value * factor for key, value in drawn.items()}
    groups = bend_groups(layers)
    gap = space * image_unit(layers, drawn)               # the space between two layers (mm)

    # The encapsulation layer on the tracks: the first layer above the tracks (not a coating), if it is an
    # encapsulation layer. It fills the space around the tracks (see wrap_pieces).
    last_track = max(i for i, layer in enumerate(layers) if layer["type"] == "tracks")
    above = [i for i in range(last_track + 1, len(layers)) if layers[i]["type"] != "electrode coating"]
    wrap = above[0] if above and layers[above[0]]["type"] == "encapsulation" else None
    track_shapes, tracks_z0 = [], None

    # z levels: the layers lie one on the other, from the bottom up, with the space between them. The materials of
    # one layer touch. The coatings float above (see below). Each material is one 3D object with its own number.
    objects, labels, z = [], [], 0.0
    for i, layer in enumerate(layers):
        if layer["type"] == "electrode coating":
            continue
        if objects:
            z += gap
        polygons = shapes(layer["shape"])
        if layer["type"] == "encapsulation" and layer["openings"] != "none":
            holes = unary_union(enlarged([p for name in split_layers(layer["openings"]) for p in shapes(name)]))
            polygons = [q for p in polygons for q in parts(p.difference(holes))]
        if layer["type"] == "tracks":
            polygons = enlarged(polygons, add_metal_rim=True)
        polygons = [q for p in polygons for q in parts(p.difference(through_holes))]   # holes through all layers
        in_view = [q for p in polygons for q in parts(p.intersection(crop))]
        radius = max(edge_radius(in_view, drawn[id(m)]) for m in layer["materials"])
        if layer["type"] == "encapsulation":              # thin strips left by the openings go (see without_slivers)
            in_view = without_slivers(in_view, radius)
        polygons = to_json(in_view, simplify, decimals)
        # Label points: only on the main shapes of the layer (at least 10 % of the area of the largest shape),
        # so that a label line never points at a small mark or a text of the layer.
        largest = max((q.area for q in in_view), default=0)
        main = [q for q in in_view if q.area >= 0.1 * largest]
        outline_points = [pt for q in main for pt in q.exterior.coords[:-1]]
        step = max(1, len(outline_points) // 400)
        label_points = [[round(x, decimals), round(y, decimals)] for x, y in outline_points[::step]]
        # The same points a little inside the edge, on the flat top face: the rounded edge is not at the outline.
        inset_points = [pt for q in main for r in parts(q.buffer(-1.5 * radius)) for pt in r.exterior.coords[:-1]]
        step = max(1, len(inset_points) // 400)
        label_inset = [[round(x, decimals), round(y, decimals)] for x, y in inset_points[::step]]
        first = len(objects)
        for m in layer["materials"]:
            objects.append(dict(index=len(objects), layer=i, name=f"{layer['name']} - {m['name']}", kind=layer["type"],
                                z0=z, z1=z + drawn[id(m)], polygons=polygons, label_points=label_points,
                                label_inset=label_inset,
                                round=min(edge_radius(in_view, drawn[id(m)]), radius)))
            z += drawn[id(m)]
        if layer["type"] == "tracks":
            tracks_z0 = objects[first]["z0"] if tracks_z0 is None else tracks_z0
            track_shapes.append((in_view, z))
        if i == wrap and track_shapes:
            # The lowest material of this layer goes down around the tracks. shift = the space above the tracks.
            o = objects[first]
            shift = o["z0"] - track_shapes[-1][1]
            pieces = wrap_pieces(in_view, [(track, top + shift) for track, top in track_shapes],
                                 tracks_z0 + shift, clearance=0.01 * min(drawn.values()), simplify=simplify)
            o["pieces"] = pieces_to_json(pieces, decimals)
            o["z_low"] = min(height for _, height in pieces) if pieces else o["z0"]
            # The edges of the grooves and of the bottom get a smaller radius: it must fit into the grooves of the
            # tracks (their width and their depth). The top edges keep the full radius.
            depth = track_shapes[-1][1] - tracks_z0
            track_polygons = [q for track, _ in track_shapes for q in track]
            o["round_low"] = min(o["round"], LOOK["round_to_width"] * narrowest_width(track_polygons), 0.45 * depth)
        middle = objects[(first + len(objects) - 1) // 2]   # the label points at the middle material
        labels.append(dict(anchor=middle["index"], name=layer["name"], text=layer_label(layer)))

    # Bending: each group bends around its hinge line. The hinge is on the face of the group that looks at the
    # tracks: the bottom face for a group above the tracks, the top face for a group below the tracks.
    track_objects = [o for o in objects if o["kind"] == "tracks"]
    tracks_bottom, tracks_top = track_objects[0]["z0"], track_objects[-1]["z1"]
    members = {}
    for o in objects:
        group, side = groups.get(o["layer"], (0, 0))
        if group:
            members.setdefault((group, side), []).append(o)
    for (group, side), group_objects in members.items():
        if cleave_angle == 0:                             # no cleave: all the layers stay flat
            break
        hinge_z = min(o.get("z_low", o["z0"]) for o in group_objects) if side > 0 else max(o["z1"] for o in group_objects)
        for o in group_objects:
            o["bend"] = dict(hinge_y=hinge, hinge_z=hinge_z, length=bend_length, angle=side * group * cleave_angle)

    # Coatings: discs above the electrodes. They float above the top face of the top layer, along its normal.
    # Each coating material is a separate disc, with a gap between the discs, and it has its own label.
    top = objects[-1]
    unit = image_unit(layers, drawn)
    coatings = []
    offset = (LOOK["coating_distance"] if coating_distance is None else coating_distance) * unit
    for i, layer in enumerate(layers):
        if layer["type"] != "electrode coating":
            continue
        polygons = [q for p in enlarged(shapes(layer["shape"])) for q in parts(p.difference(through_holes))]
        for m in layer["materials"]:
            index = len(objects) + len(coatings)
            coatings.append(dict(index=index, layer=i, name=f"{layer['name']} - {m['name']}", kind=layer["type"],
                                 offset0=offset, offset1=offset + drawn[id(m)], polygons=to_json(polygons, simplify, decimals),
                                 round=edge_radius(polygons, drawn[id(m)]),
                                 centres=[[p.centroid.x, p.centroid.y] for p in polygons]))
            labels.append(dict(anchor=index, name=m["name"], text=shown(m["thickness"])))
            offset += drawn[id(m)] + LOOK["coating_gap"] * unit

    # Dashed guide lines: from each electrode on the tracks, through the openings, up to its coating.
    with_openings = [o for o in objects if layers[o["layer"]].get("openings", "none") != "none"]
    guides = dict(centres=[[s.centroid.x, s.centroid.y] for s in enlarged(sites)] if coatings else [],
                  tracks_top=tracks_top, through=with_openings[-1]["index"] if with_openings else None)

    scene = dict(format=blender_protocol.SCENE_FORMAT,
                 objects=objects, coatings=coatings, top_object=top["index"], guides=guides, labels=labels,
                 notes=notes, width=width, region=[crop_start, length], hinge=hinge, tracks_bottom=tracks_bottom)
    paint(scene, layers)
    return scene


LOOK_ONLY = ("colour", "transparency", "surface")     # answers that change no shape: paint() puts them on


def shape_answers(layers):
    """The layers without the answers that change only the look (LOOK_ONLY): the cache key of the 3D shapes."""
    result = []
    for layer in layers:
        layer = {k: v for k, v in layer.items() if k not in LOOK_ONLY}
        layer["materials"] = [{k: v for k, v in m.items() if k not in LOOK_ONLY} for m in layer["materials"]]
        result.append(layer)
    return result


def paint(scene, layers):
    """Put the look of each material on its 3D object: colour, transparency and surface. build_scene() makes the
    objects of a layer in the order of its materials. A scene from the cache gets the look of now with no new build."""
    count = {}
    for o in scene["objects"] + scene["coatings"]:
        k = count.get(o["layer"], 0)
        count[o["layer"]] = k + 1
        layer = layers[o["layer"]]
        m = layer["materials"][k]
        o.update(colour=m["colour"], transparency=m.get("transparency", 0),
                 surface=layer.get("surface", "shiny" if o["kind"] == "electrode coating" else "plastic"))


# The 4 views that the user can select. turn = degrees around the device (0 = from the side, with the tip on
# the right; 90 = from the tip). height = degrees above the device (0 = eye level; 90 = from directly above).
VIEWS = [
    dict(name="Front, low", turn=32, height=11,
         meaning="Eye a little above device. Shows cleave and tracks."),
    dict(name="Front, high", turn=32, height=35,
         meaning="Looks down on device. Shows openings and top layer."),
    dict(name="Side", turn=0, height=4,
         meaning="Looks from side. Cleave shows as V shape."),
    dict(name="From the tip", turn=70, height=15,
         meaning="Tip points at viewer. Shows electrodes from front."),
]


def save_view_choices(views, file, angles=False):
    """Put the small test images into one image, each with its number, name and meaning.
    angles=True: the 2 angles of each view under its image (a reference for "My own angles").
    4 images: 2 rows of 2. Fewer images: one column (it fits the tall image panel of the window)."""
    columns = 2 if len(views) == 4 else 1
    rows = math.ceil(len(views) / columns)
    fig, axes = plt.subplots(rows, columns, figsize=(6 * columns, 3.8 * rows), squeeze=False)
    for number, (view, ax) in enumerate(zip(views, axes.flat), start=1):
        ax.imshow(mpimg.imread(view["file"]))
        ax.set_title(f"{number}   {view['name']}", fontsize=13, fontweight="bold", loc="left")
        if angles:
            ax.text(0.5, -0.02, f"turn {view['turn']}°, height {view['height']}°", transform=ax.transAxes,
                    fontsize=13, ha="center", va="top", color="0.25")
        ax.text(0, 1.0, view["meaning"], transform=ax.transAxes, fontsize=9, va="top", color="0.35")
        ax.axis("off")
    fig.patch.set_facecolor("white")
    fig.tight_layout()
    fig.savefig(file, dpi=110, facecolor="white")
    plt.close(fig)


def render_choices(blender, scene, test_scene, tests, choices_file, scene_file, what, note, cache):
    """Render a small test image for each option of a question (one Blender run with test_scene), and put them into
    one image (choices_file). tests = [dict(name, meaning, file)]. cache = (kind, key): if this run rendered them
    already for the same key (the user went back), keep them. Key None = always render."""
    kind, key = cache
    if key is not None and run_cache.has(kind, key) and os.path.exists(choices_file):
        return
    ui.note(note)
    with open(scene_file, "w", encoding="utf8") as f:
        json.dump(test_scene, f)
    run_blender(blender, scene, scene_file, tests[-1]["file"], what=what, images=len(tests))
    save_view_choices(tests, choices_file)
    if key is not None:
        run_cache.add(kind, key)


def whole_number_check(lowest, highest):
    def check(text):
        try:
            value = int(text)
        except ValueError:
            return f"Type a whole number from {lowest} to {highest}."
        return None if lowest <= value <= highest else f"Type a whole number from {lowest} to {highest}."
    return check




GUIDE_CHOICES = ("none", "some", "all")
SOME_GUIDES = 6          # "some" = the dashed lines of 6 electrodes, spread over the device


def guide_centres(centres, choice):
    """The electrodes that get a dashed line: all, some (SOME_GUIDES of them, spread over the device) or none."""
    if choice == "none":
        return []
    if choice == "all" or len(centres) <= SOME_GUIDES:
        return centres
    order = sorted(centres, key=lambda c: (round(c[1], 6), c[0]))          # along the device, then across
    return [order[round(i * (len(order) - 1) / (SOME_GUIDES - 1))] for i in range(SOME_GUIDES)]


def ask_guides(scene):
    """Ask how many dashed lines the image gets. A dashed line goes from an electrode, through its opening, to its
    coating. The options: no lines, the lines of SOME_GUIDES electrodes (spread over the device), or all the lines.
    With SOME_GUIDES electrodes or fewer, the middle option is not shown (it is the same as all).
    Return "none", "some" or "all"."""
    count = len(scene["guides"]["centres"])
    options = {"none": "No dashed lines"}
    if count > SOME_GUIDES:
        options["some"] = f"{SOME_GUIDES} dashed lines"
    options["all"] = f"All the dashed lines ({count})"
    details = {"some": f"{SOME_GUIDES} of the {count} electrodes, spread over the device.",
               "all": "Many lines can hide the device."}
    old = answers.PREVIOUS.get("render guide lines")
    default = old if old in options else ("some" if "some" in options else "all")
    return ui.ask_choice("Dashed lines from the electrodes to the coatings?",
                         "A line goes from an electrode, through its opening, to its coating.",
                         options, default=default, details={k: v for k, v in details.items() if k in options})


def ask_view(scene, blender, project_folder, scene_key=None):
    """Make a small test image of the device from each view, then ask the user to select one.
    If this run made the test images of the same scene already (the user went back), keep them.
    Return (turn, height) in degrees."""
    folder = os.path.join(project_folder, "5_views")
    os.makedirs(folder, exist_ok=True)
    views = [dict(v, file=os.path.join(folder, f"view_{n}.png")) for n, v in enumerate(VIEWS, start=1)]
    choices_file = os.path.join(project_folder, "5_view_choices.png")
    test_scene = dict(scene, quality="views", views=[dict(turn=v["turn"], height=v["height"], file=v["file"])
                                                    for v in views])
    render_choices(blender, scene, test_scene, views, choices_file, os.path.join(folder, "views_scene.json"),
                   what="Test images of 4 views", note="Rendering 4 test views (about 30 s) ...",
                   cache=("view images", scene_key))
    ui.show_path("4 test views:", choices_file)

    options = {str(n): f"{n}  {v['name']}" for n, v in enumerate(VIEWS, start=1)}
    details = {str(n): v["meaning"] for n, v in enumerate(VIEWS, start=1)}
    options["5"] = "5  My own angles"
    details["5"] = "Asks for 2 angles: turn around device, height above device."
    # The old answer (after "change one part" or going back) is the default: its view, or "my own angles".
    old = [int(v) for v in answers.PREVIOUS.get("render camera turn and height", "32, 11").split(",")]
    default = next((str(n) for n, v in enumerate(VIEWS, start=1) if [v["turn"], v["height"]] == old), "5")
    choice = ui.ask_choice("From which view do you want to see the device?", "", options, default=default,
                           details=details)
    if choice != "5":
        view = VIEWS[int(choice) - 1]
        return view["turn"], view["height"]
    # My own angles: the same test images, now with the angles of each view under it (no new render).
    angles_file = os.path.join(project_folder, "5_view_angles.png")
    save_view_choices(views, angles_file, angles=True)
    ui.show_path("4 test views with their angles:", angles_file)
    turn = int(ui.ask("Turn around the device, in degrees (-180 to 180)?",
                      "0 = from side, tip on right. 90 = from tip. 180 = from other side",
                      old[0], whole_number_check(-180, 180)))
    height = int(ui.ask("Height above the device, in degrees (0 to 90)?",
                        "0 = eye level. 90 = from directly above", old[1], whole_number_check(0, 90)))
    return turn, height


def render_questions(layers, has_electrodes, sites):
    """The questions of step 4 before the 3D build (Question objects), only the questions that this stack needs.
    The old answers (after going back or a change) are the default answers."""
    old = answers.PREVIOUS
    questions = []
    if has_electrodes:
        questions.append(Question(
            "render view", "choice", "Which part of the device do you want to show?",
            options={"electrodes": "Electrodes", "whole device": "Whole device"},
            details={"electrodes": "Zoom on device end with electrodes.",
                     "whole device": "Full device, from pads to electrodes."},
            default=old.get("render view", "electrodes"), label="Part of the device"))
    if sites and max(map(equal_diameter, sites)) > 3 * min(map(equal_diameter, sites)):
        questions.append(Question(
            "render small electrodes larger", "yes/no", "Draw small electrodes 2x larger?",
            "Some electrodes much smaller than others. At real size, possibly too small to see.",
            default="no" if old.get("render small electrodes larger") == "no" else "yes",
            label="Draw small electrodes 2x larger"))
    if any(layer.get("cleave") == "yes" for layer in layers):
        questions.append(Question(
            "render cleave angle", "number", "Cleave angle (degrees, 0 to 45)?",
            "angle between neighbouring cleaved layers. 0 = no cleave: layers stay flat", options=(0, 45),
            default=old.get("render cleave angle", f"{LOOK['cleave_angle']:g}"), label="Cleave angle (degrees, 0 to 45)"))

    def space_default(values):                            # no cleave: the layers need a space to show
        try:
            cleaved = float(values.get("render cleave angle", 0)) != 0
        except ValueError:
            cleaved = True
        return old.get("render space between layers", "0" if cleaved else f"{LOOK['space_flat']:g}")
    # The space is in image units: the thickest layer is 10 units. The help text gives each layer in these units.
    questions.append(Question(
        "render space between layers", "number", "Space between layers, in image units (0 to 100)?",
        f"0 = layers touch. Thickest layer in image = {UNITS_OF_THICKEST} units: {thickness_in_image_units(layers)}",
        options=(0, 100), default=space_default, label="Space between layers (image units, 0 to 100)"))
    if any(layer["type"] == "electrode coating" for layer in layers):
        questions.append(Question(
            "render coating distance", "number", "Distance from device to coatings, in image units (0 to 100)?",
            f"0 = coatings touch top layer. Thickest layer in image = {UNITS_OF_THICKEST} units", options=(0, 100),
            default=old.get("render coating distance", f"{LOOK['coating_distance']:g}"),
            label="Distance from device to coatings (image units, 0 to 100)"))
    return questions


def run(device_layers, layers, stack, project_folder, projects_folder):
    """Do step 4. Return the scene description and the render image file."""
    ui.header(4)
    if not any(layer["type"] == "tracks" for layer in layers):
        raise answers.Stop("Stack has no tracks layer. Start again and add tracks in step 3.")
    # With no coating layer, the tool finds the electrodes from the openings. When the openings come from more
    # than one mask layer (example: electrode openings and pad openings), the user selects the electrode openings.
    candidates = openings_layers(layers)
    if not any(layer["type"] == "electrode coating" for layer in layers) and len(candidates) > 1:
        ui.note("Tool turns device so electrodes are at far end. "
                "Select electrode openings, not contact pad openings.")
        answer(stack, "render electrode openings", lambda: ui.ask_layers(
            candidates, "Which mask layers draw the electrode openings?",
            default=answers.PREVIOUS.get("render electrode openings", "none")),
            is_valid=lambda text: bool(split_layers(text)) and all(n in candidates for n in split_layers(text)))
    electrode_layers = split_layers(stack.get("render electrode openings", "none")) or None
    has_electrodes = bool(electrode_shapes(device_layers, layers, electrode_layers=electrode_layers))
    sites = electrode_shapes(device_layers, layers, electrode_layers=electrode_layers)
    values = answer_page(stack, render_questions(layers, has_electrodes, sites),
                         "Values for the 3D shapes. Then test images of the views.")
    view = values.get("render view", "whole device")
    enlarge = values.get("render small electrodes larger", "no")
    cleave_angle = float(values.get("render cleave angle", 0.0))
    space = float(values["render space between layers"])
    coating_distance = float(values.get("render coating distance", LOOK["coating_distance"]))

    # The same answers give the same scene: going back does not build it again. The look (colour, transparency,
    # surface) changes no shape: the key of the shapes leaves it out, and paint() puts the look of now on the scene.
    # The test images show the look: their key has all the answers.
    common = [[stack.get(k) for k in ("dxf file", "unit", "layer names", "outline layer", "device number",
                                      "through holes", "render electrode openings")],
              view, enlarge, cleave_angle, space, coating_distance]
    shape_key = json.dumps(common + [shape_answers(layers)], sort_keys=True, default=str)
    key = json.dumps(common + [layers], sort_keys=True, default=str)
    def build():
        with ui.working("Making 3D shapes of layers ..."):
            return build_scene(device_layers, layers, stack, view, enlarge, cleave_angle, space, coating_distance)
    scene = copy.deepcopy(run_cache.get("scene", shape_key, build))
    paint(scene, layers)
    blender = find_blender(projects_folder)
    check_blender_version(blender)
    ui.note(f"Blender: {blender}")

    # The camera angles, saved as one line: "turn, height" (degrees).
    def angles_valid(text):
        values = text.split(",")
        return (len(values) == 2 and whole_number_check(-180, 180)(values[0].strip()) is None
                and whole_number_check(0, 90)(values[1].strip()) is None)
    angles = answer(stack, "render camera turn and height", lambda: "%d, %d" % ask_view(scene, blender, project_folder, key),
                    is_valid=angles_valid)
    turn, height = (int(v) for v in angles.split(","))
    scene["camera"] = dict(turn=turn, height=height)

    # Two options for the image: the dashed guide lines (only with a coating) and the labels.
    if scene["coatings"] and scene["guides"]["centres"]:
        guides = answer(stack, "render guide lines", lambda: ask_guides(scene), is_valid=lambda v: v in GUIDE_CHOICES)
        scene["guides"]["centres"] = guide_centres(scene["guides"]["centres"], guides)
    scene["show labels"] = answer(stack, "render labels", lambda: ui.ask_yes_no(
        "Show labels?", "Labels give name and real thickness of each layer. No = image with no text.",
        default="n" if answers.PREVIOUS.get("render labels") == "no" else "y"),
        is_valid=lambda v: v in ("yes", "no"))

    # The quality is not saved in the stack: you select it again at each run.
    scene["quality"] = ui.ask_choice(
        "Image quality?", "", {"preview": "Preview", "final": "Final"}, default="preview",
        details={"preview": "Small image (1280 x 720). About 1 min. Good for a check.",
                 "final": "Large image (2560 x 1440). About 1 min with graphics card, up to 20 min without."})

    scene_file = os.path.join(project_folder, "5_scene.json")
    with open(scene_file, "w", encoding="utf8") as f:
        json.dump(scene, f)
    image_file = os.path.join(project_folder, "5_render.png")
    run_blender(blender, scene, scene_file, image_file, what="Rendering")
    return scene, image_file
