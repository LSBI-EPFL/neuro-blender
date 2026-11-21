"""
Image regression test: render the test design (tests/design/) at test quality (640 x 360, about 10 s) and compare
the image with the saved reference image tests/reference/linear_probe_render.png. A change of the geometry or the
look shows as a large difference. Render noise is allowed.

Run:  python tests/test_render.py              (needs Blender; with no Blender, the test is skipped)
      python tests/test_render.py --update     (save the new image as the reference, after a wanted change)
"""
import contextlib
import json
import os
import shutil
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
sys.path.insert(0, REPO)

import matplotlib.image as mpimg
import numpy as np

from backend import answers, step1_read_mask, step2_pick_device, step3_layer_questions, ui
from backend import step4_build_scene as s4

REFERENCE = os.path.join(HERE, "reference", "linear_probe_render.png")
MASK = os.path.join(REPO, "tests", "design", "linear_probe.dxf")
# Two renders on one computer are the same, so the limits are tight: a small change of the look fails the test (no
# rounded edges changes about 1 % of the pixels). The reference belongs to one computer (graphics card, Blender
# version): on another computer, check the image and save it again with --update.
ALLOWED_PIXELS = 0.002      # at most 0.2 % of the pixels may differ by more than ALLOWED_DIFFERENCE
ALLOWED_DIFFERENCE = 0.1


class _Bar:
    def __enter__(self):
        return self

    def __exit__(self, *error):
        return False

    def advance(self, text=None):
        pass

    def update(self, text):
        pass


class Silent:
    """A front end that shows nothing. All the answers come from the answers file of the test design."""
    def __getattr__(self, name):
        if name in ("working",):
            return lambda text: contextlib.nullcontext()
        if name == "progress":
            return lambda text, total: _Bar()
        return lambda *args, **kwargs: None


def find_blender():
    """The Blender program, or None. (No window: this test never asks.)"""
    saved = os.path.join(REPO, "projects", "blender.txt")
    if os.path.exists(saved) and os.path.exists(open(saved, encoding="utf8").read().strip()):
        return open(saved, encoding="utf8").read().strip()
    import glob
    candidates = [shutil.which("blender") or ""] + sorted(
        glob.glob(r"C:\Program Files\Blender Foundation\Blender*\blender.exe"), reverse=True)
    return next((c for c in candidates if c and os.path.exists(c)), None)


def render(folder):
    """Build the scene of the test design with its saved answers and render it at test quality. Return the image."""
    ui.use(Silent())
    stack = answers.read_stack(os.path.join(REPO, "tests", "design", "linear_probe_stack.yaml"))
    stack["dxf file"] = MASK
    layers = step1_read_mask.run(MASK, stack, folder)
    device = step2_pick_device.run(layers, stack, folder)
    stack_layers = step3_layer_questions.run(device, stack, folder)
    scene = s4.build_scene(device, stack_layers, stack, "electrodes", "no", cleave_angle=9, space=0,
                           coating_distance=20)
    scene.update(camera=dict(turn=32, height=11), quality="views")
    scene_file, image_file = os.path.join(folder, "scene.json"), os.path.join(folder, "render.png")
    with open(scene_file, "w", encoding="utf8") as f:
        json.dump(scene, f)
    s4.run_blender(blender, scene, scene_file, image_file, what="Test render")
    return image_file


blender = find_blender()
if blender is None:
    print("SKIP  image regression test: no Blender program found")
    sys.exit(0)
with tempfile.TemporaryDirectory() as folder:
    image = render(folder)
    if "--update" in sys.argv or not os.path.exists(REFERENCE):
        os.makedirs(os.path.dirname(REFERENCE), exist_ok=True)
        shutil.copy(image, REFERENCE)
        print(f"SAVED  new reference image: {REFERENCE}")
        sys.exit(0)
    new, old = mpimg.imread(image), mpimg.imread(REFERENCE)
if new.shape != old.shape:
    print(f"FAIL  image regression test: image size {new.shape} is not the reference size {old.shape}")
    sys.exit(1)
different = (np.abs(new - old).max(axis=2) > ALLOWED_DIFFERENCE).mean()
ok = different <= ALLOWED_PIXELS
print(f"{'PASS' if ok else 'FAIL'}  image regression test: {100 * different:.2f} % of the pixels differ "
      f"(allowed: {100 * ALLOWED_PIXELS:.1f} %)")
sys.exit(0 if ok else 1)
