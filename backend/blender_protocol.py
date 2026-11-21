"""
The agreement between the tool and its Blender script (blender_render.py). Both sides import this file, so that
the two sides cannot disagree.

  - The scene file (5_scene.json) has the value "format": SCENE_FORMAT and the keys in SCENE_KEYS.
  - Blender writes its progress as one line for each event: PREFIX + JSON. Example:
        NEURO_BLENDER {"event": "built", "name": "Top PI - PI"}
    Events: "built" (one 3D object), "device" (graphics card or processor), "rendering", "saved view" (one test
    image), "saved" (the .blend file or the final image), "warning" (a problem that does not stop the render).
"""
import json

PREFIX = "NEURO_BLENDER "
SCENE_FORMAT = 1
SCENE_KEYS = ("format", "objects", "coatings", "top_object", "guides", "labels", "width", "quality")
MINIMUM_BLENDER = (5, 0)          # the tool is tested with Blender 5.0


def message(event, **values):
    """One progress line (Blender side)."""
    return PREFIX + json.dumps(dict(event=event, **values))


def read(line):
    """A progress line -> its event as a dictionary. Any other line of Blender output -> None."""
    if not line.startswith(PREFIX):
        return None
    try:
        return json.loads(line[len(PREFIX):])
    except ValueError:
        return None
