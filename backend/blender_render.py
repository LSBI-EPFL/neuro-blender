"""
The Blender part of Neuro Blender. Blender runs this file; you do not run it yourself.
step4_build_scene.py starts it like this:

    blender --background --factory-startup --python blender_render.py -- 5_scene.json 5_render.png

It reads the scene file (all the shapes, thicknesses, colours and bends), builds the 3D device,
places the camera and the lights, and renders the image on a transparent background.
It also writes 5_render_points.json (one image point on each layer, for the labels of step 5)
and 5_render.blend (the scene, to open in Blender).

Units: 1 Blender unit = 1 mm.
"""
import json
import math
import os
import sys

import bmesh
import bpy
import numpy as np
from bpy_extras.object_utils import world_to_camera_view
from mathutils import Matrix, Vector, geometry

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import blender_protocol as protocol                # the agreement with the tool (scene format, progress lines)

scene_file, image_file = (os.path.abspath(f) for f in sys.argv[sys.argv.index("--") + 1:][:2])   # full paths:
# Blender reads a relative path from the folder of the saved .blend file, not from the current folder.
S = json.load(open(scene_file, encoding="utf8"))
_missing = [key for key in protocol.SCENE_KEYS if key not in S]
if _missing or S.get("format") != protocol.SCENE_FORMAT:
    print(f"Neuro Blender: the scene file does not fit this Blender script (format {S.get('format')}, "
          f"missing keys: {', '.join(_missing) or 'none'}).", flush=True)
    sys.exit(1)
if tuple(bpy.app.version[:2]) < protocol.MINIMUM_BLENDER:
    print(f"Neuro Blender needs Blender {'.'.join(map(str, protocol.MINIMUM_BLENDER))} or newer "
          f"(this is Blender {bpy.app.version_string}).", flush=True)
    sys.exit(1)
W = S["width"]                                   # device width (mm): the scale of all the look values
MERGE = W * 1e-7                                  # points closer than this are one point (from the size, not in mm)

LENS = 70                                         # camera lens (mm): a longer lens = a flatter view
QUALITY = {"views": dict(resolution=(640, 360), samples=16),        # the small test images of the views
           "preview": dict(resolution=(1280, 720), samples=32),
           "final": dict(resolution=(2560, 1440), samples=256)}


def say(event, **values):
    """Tell the tool about progress: one line, PREFIX + JSON (see blender_protocol.py)."""
    print(protocol.message(event, **values), flush=True)


# ───────────────────────────────────────────────────────── bending ──

class Bend:
    """How one cleaved layer bends. It is flat up to the hinge line (y = hinge_y), then it turns smoothly
    over the bend length up to its full angle, and then it continues straight.
    The face at z = hinge_z keeps its length; the rest of the layer keeps its thickness."""

    def __init__(self, b):
        self.y0, self.z0, self.length = b["hinge_y"], b["hinge_z"], b["length"]
        self.full = math.radians(b["angle"])
        self.s = np.linspace(0.0, self.length, 400)
        t = self.s / self.length
        self.phi = self.full * t * t * (3 - 2 * t)                     # smooth start and smooth end
        step = self.s[1] - self.s[0]
        self.cy = np.concatenate([[0.0], np.cumsum((np.cos(self.phi[1:]) + np.cos(self.phi[:-1])) / 2 * step)])
        self.cz = np.concatenate([[0.0], np.cumsum((np.sin(self.phi[1:]) + np.sin(self.phi[:-1])) / 2 * step)])

    def frame(self, y):
        """Return (y, z, angle) of the hinge face at the flat position y."""
        s = y - self.y0
        if s <= 0:
            return y, self.z0, 0.0
        if s <= self.length:
            return (self.y0 + float(np.interp(s, self.s, self.cy)), self.z0 + float(np.interp(s, self.s, self.cz)),
                    float(np.interp(s, self.s, self.phi)))
        extra = s - self.length                                         # after the bend: straight
        return (self.y0 + self.cy[-1] + extra * math.cos(self.full), self.z0 + self.cz[-1] + extra * math.sin(self.full),
                self.full)

    def move(self, x, y, z):
        """Move one point of the flat layer to its place in the bent layer."""
        fy, fz, a = self.frame(y)
        h = z - self.z0
        return Vector((x, fy - h * math.sin(a), fz + h * math.cos(a)))


class NoBend:
    def frame(self, y):
        return y, 0.0, 0.0

    def move(self, x, y, z):
        return Vector((x, y, z))


def surface_point(bend, x, y, z, offset):
    """The point at `offset` mm along the normal of a layer face (height z) above the flat point (x, y).
    Also return the two directions of that face: along it (t) and its normal (n)."""
    _, _, a = bend.frame(y)
    t, n = Vector((0, math.cos(a), math.sin(a))), Vector((0, -math.sin(a), math.cos(a)))
    return bend.move(x, y, z) + offset * n, t, n


# ───────────────────────────────────────────────────────── meshes ──

def add_solid(bm, exterior, holes, z0, z1, place=None):
    """Add one solid: a 2D polygon (with holes) between the heights z0 and z1.
    place(x, y, z) -> Vector moves each point (no place: the point stays where it is)."""
    rings = [exterior] + holes
    place = place or (lambda x, y, z: Vector((x, y, z)))
    top = [[bm.verts.new(place(x, y, z1)) for x, y in r] for r in rings]
    bottom = [[bm.verts.new(place(x, y, z0)) for x, y in r] for r in rings]
    flat_rings = [[Vector((x, y, 0)) for x, y in r] for r in rings]
    for vertices, flip in ((top, False), (bottom, True)):
        flat = [v for r in vertices for v in r]
        for tri in geometry.tessellate_polygon(flat_rings):
            try:
                bm.faces.new([flat[i] for i in (tri[::-1] if flip else tri)])
            except ValueError:
                pass                                                    # a face that exists already
    for upper, lower in zip(top, bottom):
        n = len(upper)
        for i in range(n):
            j = (i + 1) % n
            try:
                bm.faces.new([lower[i], lower[j], upper[j], upper[i]])
            except ValueError:
                pass


def add_stepped_solid(bm, pieces, z_top, overlap):
    """Add one closed solid with a flat top face (height z_top) and a stepped bottom face.
    pieces = the areas of the bottom face, each with its own bottom height ("z"). Two pieces next to each other
    have the same border points. Example: the encapsulation layer on the tracks goes down around the tracks.

    The solid has: the top face, one bottom face for each piece, and vertical walls. A wall is at the outer border
    (from the bottom of the piece up to the top), or between two pieces with different bottoms (the step)."""
    vertices = {}

    def vertex(point, z):
        key = (point[0], point[1], round(z / MERGE))
        if key not in vertices:
            vertices[key] = bm.verts.new((point[0], point[1], z))
        return vertices[key]

    def new_face(face):
        if len(set(face)) == len(face) >= 3:
            try:
                bm.faces.new(face)
            except ValueError:
                pass                                                    # a face that exists already

    levels, sides, all_rings = {}, {}, []                 # levels: the heights of the vertices at each point
    for piece in pieces:
        z = piece["z"] - overlap                          # into the layer below: no two faces in one plane
        rings = []
        for ring in [piece["exterior"]] + piece["holes"]:
            ring = [tuple(p) for i, p in enumerate(ring) if tuple(p) != tuple(ring[i - 1])]   # no repeated points
            if len(ring) >= 3:
                rings.append(ring)
        if not rings:
            continue
        all_rings.append((rings, z))
        for ring in rings:
            for a, b in zip(ring, ring[1:] + ring[:1]):
                levels.setdefault(a, set()).update((z, z_top))
                sides.setdefault(tuple(sorted((a, b))), []).append(z)

    for rings, z in all_rings:                            # the top face and the bottom face of each piece
        points = [p for ring in rings for p in ring]
        for tri in geometry.tessellate_polygon([[Vector((x, y, 0)) for x, y in ring] for ring in rings]):
            new_face([vertex(points[i], z_top) for i in tri])
            new_face([vertex(points[i], z) for i in tri[::-1]])

    for (a, b), bottoms in sides.items():                 # the walls
        low, high = (bottoms[0], z_top) if len(bottoms) == 1 else (min(bottoms[:2]), max(bottoms[:2]))
        if high - low < MERGE:
            continue                                      # two pieces with the same bottom: no wall
        # All the vertices on the two vertical edges of the wall are part of the wall (no open gaps).
        up_b = sorted(z for z in levels[b] if low < z < high)
        down_a = sorted((z for z in levels[a] if low < z < high), reverse=True)
        new_face([vertex(a, low), vertex(b, low)] + [vertex(b, z) for z in up_b] + [vertex(b, high), vertex(a, high)]
                 + [vertex(a, z) for z in down_a])


def finish(name, bm, material):
    bmesh.ops.remove_doubles(bm, verts=bm.verts[:], dist=MERGE)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
    mesh = bpy.data.meshes.new(name)
    open_edges = sum(1 for e in bm.edges if len(e.link_faces) < 2)
    if open_edges:                                  # a hole in the surface: the render can show dark areas
        say("warning", text=f"{name}: {open_edges} open edges (holes in the surface). The image can show dark areas.")
    bm.to_mesh(mesh)
    bm.free()
    mesh.materials.append(material)
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.scene.collection.objects.link(obj)
    return obj


def join_flat_faces(bm):
    """Make good faces for the bevel. First join the triangles of each flat face and remove the points in the middle
    of straight edges (the triangles of the first fill are long and thin). Then split the joined faces again into
    well-shaped triangles. A large joined face with many openings keeps edges from its openings to its outer line at
    very small angles: the bevel slid along these edges and made long spikes through the layer (seen on layers with
    many openings)."""
    bmesh.ops.remove_doubles(bm, verts=bm.verts[:], dist=MERGE)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
    bmesh.ops.dissolve_limit(bm, angle_limit=math.radians(1), verts=bm.verts[:], edges=bm.edges[:])
    bmesh.ops.triangulate(bm, faces=bm.faces[:], quad_method="BEAUTY", ngon_method="BEAUTY")
    bm.normal_update()


def mark_round_edges(bm, low_z=None, low_ratio=1.0):
    """Mark the edges to round (bevel weight): the edges sharper than 30° get the weight 1.
    For the encapsulation layer on the tracks, the edges below its flat part (lower than low_z: the grooves and the
    bottom) get the weight low_ratio: a smaller radius, so that the rounded edges fit into the narrow grooves.
    Do this on the flat layer, before the bend: the parts of a cut edge keep its weight."""
    weight = bm.edges.layers.float.get("bevel_weight_edge") or bm.edges.layers.float.new("bevel_weight_edge")
    for e in bm.edges:
        if len(e.link_faces) == 2 and e.calc_face_angle(0) > math.radians(30):
            low = low_z is not None and min(v.co.z for v in e.verts) < low_z - MERGE
            e[weight] = low_ratio if low else 1.0


def cut_for_bend(bm, bend):
    """Add cut lines across the layer in the bend zone, so that the layer bends smoothly."""
    for y in np.linspace(bend.y0, bend.y0 + bend.length, 60):
        bmesh.ops.bisect_plane(bm, geom=bm.verts[:] + bm.edges[:] + bm.faces[:], dist=MERGE,
                               plane_co=(0.0, float(y), 0.0), plane_no=(0.0, 1.0, 0.0))


def tube(bm, a, b, radius):
    d = b - a
    if d.length < MERGE:
        return
    matrix = Matrix.Translation((a + b) / 2) @ d.to_track_quat("Z", "Y").to_matrix().to_4x4()
    bmesh.ops.create_cone(bm, cap_ends=True, segments=8, radius1=radius, radius2=radius, depth=d.length, matrix=matrix)


def dashed_line(bm, points, radius, dash):
    for a, b in zip(points[:-1], points[1:]):
        direction, length = (b - a).normalized(), (b - a).length
        s = 0.0
        while s < length:
            tube(bm, a + direction * s, a + direction * min(s + dash, length), radius)
            s += 1.8 * dash


# ───────────────────────────────────────────────────────── materials ──

def linear(hex_colour):
    """Hex colour (sRGB, as the user sees it) -> linear RGB (what Blender uses)."""
    rgb = [int(hex_colour.lstrip("#")[i:i + 2], 16) / 255 for i in (0, 2, 4)]
    return [c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4 for c in rgb]


def material(name, hex_colour, surface, transparency=0):
    """A material in the colour of the user. transparency in % (0 = solid)."""
    m = bpy.data.materials.new(name)
    if m.node_tree is None:                         # Blender 5 makes the node tree already
        m.use_nodes = True
    p = next(n for n in m.node_tree.nodes if n.type == "BSDF_PRINCIPLED")
    p.inputs["Base Color"].default_value = (*linear(hex_colour), 1)
    p.inputs["Alpha"].default_value = 1 - transparency / 100
    look = {"shiny": dict(metallic=1.0, roughness=0.22),
            "matte": dict(metallic=0.0, roughness=0.75),
            "plastic": dict(metallic=0.0, roughness=0.55)}[surface]
    p.inputs["Metallic"].default_value = look["metallic"]
    p.inputs["Roughness"].default_value = look["roughness"]
    return m


def emission(name, hex_colour):
    m = bpy.data.materials.new(name)
    if m.node_tree is None:                         # Blender 5 makes the node tree already
        m.use_nodes = True
    nodes = m.node_tree.nodes
    for n in list(nodes):
        if n.type == "BSDF_PRINCIPLED":
            nodes.remove(n)
    e = nodes.new("ShaderNodeEmission")
    e.inputs["Color"].default_value = (*linear(hex_colour), 1)
    m.node_tree.links.new(e.outputs[0], next(n for n in nodes if n.type == "OUTPUT_MATERIAL").inputs["Surface"])
    return m


def round_edges(obj, radius):
    """Round the sharp edges of the object (a fillet), with a bevel of this radius (mm).
    Only the marked edges get the bevel (mark_round_edges). step4 limits the radius for each object, so that the
    bevels never cross. ("Clamp overlap" is off: Blender calculates its limit one time for the full object, and one
    short edge makes all the edges sharp.)
    The faces have a flat shading, and the bevel has 10 steps, so that the round edge looks smooth. (Smooth shading
    gave dark areas on the large bent faces of a layer with many openings.)
    "Loop slide" is off: the bevel keeps an even width and does not slide along the edges of the flat faces (a
    slide along an edge at a small angle made spikes)."""
    if radius <= 0:
        return
    bevel = obj.modifiers.new("Round edges", "BEVEL")
    bevel.width = radius
    bevel.segments = 10
    bevel.limit_method = "WEIGHT"                   # the radius of each edge = width x its weight
    bevel.use_clamp_overlap = False
    bevel.loop_slide = False
    bevel.harden_normals = False


# ───────────────────────────────────────────────────────── build ──

def build_device():
    """Build all the layers and the coatings. Return {layer index: object} and the bend of each layer."""
    made, bends = {}, {}
    overlap = 0.02 * min(o["z1"] - o["z0"] for o in S["objects"])     # no two faces in one plane
    for o in S["objects"]:
        bend = Bend(o["bend"]) if "bend" in o else NoBend()
        bends[o["index"]] = bend
        bm = bmesh.new()
        if o.get("pieces"):                         # the encapsulation layer on the tracks: down around the tracks
            add_stepped_solid(bm, o["pieces"], o["z1"], overlap)
        else:
            for p in o["polygons"]:
                add_solid(bm, p["exterior"], p["holes"], o["z0"] - overlap, o["z1"])
        join_flat_faces(bm)
        if o.get("round"):
            mark_round_edges(bm, o["z0"] if o.get("pieces") else None, o.get("round_low", o["round"]) / o["round"])
        if "bend" in o:
            cut_for_bend(bm, bend)
            for v in bm.verts:
                v.co = bend.move(*v.co)
        made[o["index"]] = finish(o["name"], bm, material(o["name"], o["colour"], o["surface"], o.get("transparency", 0)))
        round_edges(made[o["index"]], o.get("round", 0))
        say("built", name=o["name"])

    # Coatings: one disc above each electrode, along the normal of the top face of the top layer.
    top = next(o for o in S["objects"] if o["index"] == S["top_object"])
    top_bend = bends[top["index"]]
    for c in S["coatings"]:
        bm = bmesh.new()
        for p, (xc, yc) in zip(c["polygons"], c["centres"]):
            base, t, n = surface_point(top_bend, xc, yc, top["z1"], 0.0)
            x_axis = Vector((1, 0, 0))
            place = lambda x, y, z: base + (x - xc) * x_axis + (y - yc) * t + z * n
            add_solid(bm, p["exterior"], p["holes"], c["offset0"], c["offset1"], place)
        join_flat_faces(bm)
        mark_round_edges(bm)
        made[c["index"]] = finish(c["name"], bm, material(c["name"], c["colour"], c["surface"], c.get("transparency", 0)))
        round_edges(made[c["index"]], c.get("round", 0))
        say("built", name=c["name"])

    if S["guides"]["centres"] and S["coatings"]:
        add_guides(bends, S["guides"]["centres"])
    return made, bends


def add_guides(bends, centres):
    """Dashed guide lines: from each electrode (centres = its x, y) on the tracks, through the opening, up to the
    first coating. Return the object."""
    g = S["guides"]
    top = next(o for o in S["objects"] if o["index"] == S["top_object"])
    through = next((o for o in S["objects"] if o["index"] == g["through"]), None)
    bm = bmesh.new()
    for xc, yc in centres:
        points = [Vector((xc, yc, g["tracks_top"]))]
        if through:
            points.append(bends[through["index"]].move(xc, yc, (through["z0"] + through["z1"]) / 2))
        points.append(surface_point(bends[top["index"]], xc, yc, top["z1"], S["coatings"][0]["offset0"])[0])
        dashed_line(bm, points, radius=0.0025 * W, dash=0.03 * W)
    guides = finish("Guide lines", bm, emission("Guide line", "#1d2430"))
    guides.visible_shadow = False
    return guides


def place_camera(objects, turn, height):
    """Point the camera at the device and move it back until the whole device is in the image.
    turn:   degrees around the device. 0 = from the side (the tip on the right), 90 = from the tip.
    height: degrees above the device. 0 = eye level with the device, 90 = from directly above."""
    sc = bpy.context.scene
    points = [o.matrix_world @ v.co for o in objects for v in o.data.vertices]
    low = Vector([min(p[i] for p in points) for i in range(3)])
    high = Vector([max(p[i] for p in points) for i in range(3)])
    centre = (low + high) / 2
    az, el = math.radians(turn), math.radians(height)
    direction = Vector((math.cos(el) * math.cos(az), math.cos(el) * math.sin(az), math.sin(el)))

    data = bpy.data.cameras.new("Camera")
    data.lens = LENS
    data.clip_start, data.clip_end = 0.01, 100000
    cam = bpy.data.objects.new("Camera", data)
    sc.collection.objects.link(cam)
    sc.camera = cam
    cam.location = centre + direction * 10 * (high - low).length
    cam.rotation_euler = (-direction).to_track_quat("-Z", "Y").to_euler()
    bpy.context.view_layer.update()
    location, _ = cam.camera_fit_coords(bpy.context.evaluated_depsgraph_get(), [c for p in points for c in p])
    cam.location = centre + (Vector(location) - centre) * 1.3            # a margin around the device
    return cam, centre, (high - low).length


def add_light(name, centre, distance, azimuth, elevation, power, size, colour=(1, 1, 1)):
    light = bpy.data.lights.new(name, "AREA")
    light.energy, light.size, light.color = power, size, colour
    obj = bpy.data.objects.new(name, light)
    bpy.context.scene.collection.objects.link(obj)
    az, el = math.radians(azimuth), math.radians(elevation)
    obj.location = centre + distance * Vector((math.cos(el) * math.cos(az), math.cos(el) * math.sin(az), math.sin(el)))
    obj.rotation_euler = (centre - obj.location).to_track_quat("-Z", "Y").to_euler()
    obj.visible_camera = False


def add_studio(centre, size, cam_az):
    """Soft studio light: a key light, a fill light, a top light and a back light, plus a grey world.
    The lights turn with the camera (cam_az = the camera turn), so each view gets the same light."""
    d = 3 * size
    k = d * d                                       # the light power grows with the square of the distance
    add_light("Key", centre, d, cam_az + 45, 50, 16 * k, 1.2 * size, (1.0, 0.98, 0.95))
    add_light("Fill", centre, d, cam_az - 60, 20, 6 * k, 1.5 * size)
    add_light("Top", centre, d, 0, 85, 4 * k, 1.5 * size)
    add_light("Back", centre, d, cam_az + 180, 25, 10 * k, 1.2 * size, (0.9, 0.94, 1.0))
    world = bpy.data.worlds.new("World")
    bpy.context.scene.world = world
    if world.node_tree is None:
        world.use_nodes = True
    world.node_tree.nodes["Background"].inputs[0].default_value = (0.20, 0.205, 0.215, 1)


def render_settings():
    sc = bpy.context.scene
    q = QUALITY[S["quality"]]
    sc.render.engine = "CYCLES"
    sc.cycles.samples = q["samples"]
    sc.cycles.use_denoising = True
    sc.render.resolution_x, sc.render.resolution_y = q["resolution"]
    sc.render.resolution_percentage = 100
    sc.render.film_transparent = True
    sc.render.image_settings.file_format = "PNG"
    sc.render.image_settings.color_mode = "RGBA"
    try:
        sc.view_settings.view_transform = "AgX"
    except TypeError:
        pass
    try:                                            # use the graphics card if Blender can
        prefs = bpy.context.preferences.addons["cycles"].preferences
        for kind in ("OPTIX", "CUDA", "HIP", "ONEAPI", "METAL"):
            try:
                prefs.compute_device_type = kind
            except TypeError:
                continue
            prefs.get_devices()
            if any(d.type != "CPU" for d in prefs.devices):
                for d in prefs.devices:
                    d.use = d.type != "CPU"
                sc.cycles.device = "GPU"
                say("device", name=kind)
                return
    except Exception as error:
        say("warning", text=f"Graphics card setup failed ({error}). Render on the processor (slower).")
    say("device", name="processor")


def label_points(made, cam, bends):
    """One image point on each layer, for the labels: the visible point of the layer farthest to the right.
    First try the top face of the layer (points a little inside its rounded edge). If the layer above hides the
    top face (example: no space between the layers), try the middle of its side wall."""
    sc = bpy.context.scene
    w, h = sc.render.resolution_x, sc.render.resolution_y
    depsgraph = bpy.context.evaluated_depsgraph_get()
    out = []
    for index, obj in made.items():
        layer = next((o for o in S["objects"] if o["index"] == index), None)
        if layer and layer.get("label_points"):           # the main shapes of the layer
            middle = (layer["z0"] + layer["z1"]) / 2
            tries = [[bends[index].move(x, y, layer["z1"]) for x, y in layer.get("label_inset") or layer["label_points"]],
                     [bends[index].move(x, y, middle) for x, y in layer["label_points"]]]
        else:                                             # a coating disc: all its points
            tries = [[obj.matrix_world @ v.co for v in obj.data.vertices]]
        chosen = None
        for points in tries:
            points.sort(key=lambda p: -world_to_camera_view(sc, cam, p).x)
            for p in points[:400]:                  # the first point that the camera can see
                direction = (p - cam.location)
                hit, location, _, _, hit_object, _ = sc.ray_cast(depsgraph, cam.location, direction.normalized())
                if hit and hit_object.name == obj.name and (location - p).length < 0.01 * W:
                    chosen = p
                    break
            if chosen:
                break
        chosen = chosen or tries[0][0]
        v = world_to_camera_view(sc, cam, chosen)
        out.append(dict(index=index, xy=[round(v.x * w, 1), round((1 - v.y) * h, 1)]))
    return dict(resolution=[w, h], points=out)


def remove_camera_and_lights():
    for collection in (bpy.data.lights, bpy.data.cameras, bpy.data.worlds):
        for item in list(collection):
            collection.remove(item)


def render_views(made):
    """Render one small test image for each view in S["views"] (for the view question of step 4)."""
    render_settings()
    for view in S["views"]:
        remove_camera_and_lights()
        cam, centre, size = place_camera(list(made.values()), view["turn"], view["height"])
        add_studio(centre, size, view["turn"])
        bpy.context.scene.render.filepath = view["file"]
        bpy.ops.render.render(write_still=True)
        say("saved view", file=view["file"])


def main():
    for collection in (bpy.data.objects, bpy.data.meshes, bpy.data.materials, bpy.data.lights,
                       bpy.data.cameras, bpy.data.worlds):
        for item in list(collection):
            collection.remove(item)
    made, bends = build_device()
    if "views" in S:
        render_views(made)
        return
    cam, centre, size = place_camera(list(made.values()), S["camera"]["turn"], S["camera"]["height"])
    add_studio(centre, size, S["camera"]["turn"])
    render_settings()
    points = label_points(made, cam, bends)
    with open(image_file[:-4] + "_points.json", "w", encoding="utf8") as f:
        json.dump(points, f, indent=1)
    bpy.context.scene.render.filepath = image_file
    blend_file = image_file[:-4] + ".blend"             # the scene, to open and change in Blender by hand
    bpy.context.preferences.filepaths.save_version = 0   # no old copy (.blend1) when the file exists already
    bpy.ops.wm.save_as_mainfile(filepath=blend_file)
    say("saved", file=blend_file)
    say("rendering")
    bpy.ops.render.render(write_still=True)
    say("saved", file=image_file)


main()
