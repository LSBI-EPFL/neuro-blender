"""
The Blender program: find it, check its version, run it with blender_render.py, and stop it.

step4_build_scene.py uses these functions. The progress lines of Blender follow blender_protocol.py.
"""
import glob
import os
import re
import shutil
import subprocess

from backend import answers, blender_protocol, run_cache, ui

HERE = os.path.dirname(os.path.abspath(__file__))
# Windows: Blender opens no console window of its own (the double-click start file runs the tool with no terminal).
# Its output comes through a pipe. On other systems the value is 0: no change.
NO_CONSOLE = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def blender_version(blender):
    """The version of a Blender program, as (major, minor), or None if it cannot tell. One check in a run."""
    def read():
        try:
            text = subprocess.run([blender, "--version"], capture_output=True, text=True, timeout=60,
                                  creationflags=NO_CONSOLE).stdout
            match = re.search(r"Blender (\d+)\.(\d+)", text)
            return (int(match.group(1)), int(match.group(2))) if match else None
        except (OSError, subprocess.SubprocessError):
            return None
    return run_cache.get("blender version", blender, read)


def check_blender_version(blender):
    """Stop with a clear message before the first render if the Blender program is too old."""
    version = blender_version(blender)
    minimum = blender_protocol.MINIMUM_BLENDER
    if version is not None and version < minimum:
        raise answers.Stop(f"Blender {version[0]}.{version[1]} is too old. Neuro Blender needs Blender "
                           f"{minimum[0]}.{minimum[1]} or newer: https://www.blender.org")


def find_blender(projects_folder):
    """Find the Blender program. The path is saved in projects/blender.txt (it is the same for all designs)."""
    saved = os.path.join(projects_folder, "blender.txt")
    if os.path.exists(saved):
        path = open(saved, encoding="utf8").read().strip()
        if os.path.exists(path):
            return path
    candidates = [shutil.which("blender") or ""]
    candidates += sorted(glob.glob(r"C:\Program Files\Blender Foundation\Blender*\blender.exe"), reverse=True)
    candidates += ["/Applications/Blender.app/Contents/MacOS/Blender"]
    path = next((c for c in candidates if c and os.path.exists(c)), None)
    if not path:
        ui.warn("Blender not found. Select Blender program in window.\n"
                "No Blender? Download from https://www.blender.org.")
        path = ui.pick_file("Select Blender program", os.path.expanduser("~"), [("Program", "*")])
        if not path:
            raise answers.Stop("No Blender program selected.")
    os.makedirs(projects_folder, exist_ok=True)
    with open(saved, "w", encoding="utf8") as f:
        f.write(path)
    return path


_blender = None       # the Blender program that runs now (so that stop_blender can stop it)


def stop_blender():
    """Stop the Blender program that runs now, if there is one (example: the user closes the window)."""
    if _blender is not None and _blender.poll() is None:
        _blender.terminate()


def run_blender(blender, scene, scene_file, image_file, what="Rendering", images=1):
    """Run Blender in the background with blender_render.py. Show a progress bar.

    The bar counts the stages that Blender reports: one for each 3D object that it builds, then one for each
    image that it saves. (Blender does not report the progress inside one image.)
    If Blender stops with an error, the script shows the last lines of its output."""
    script = os.path.join(HERE, "blender_render.py")
    command = [blender, "--background", "--factory-startup", "--python", script, "--", scene_file, image_file]
    global _blender
    process = _blender = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                                          encoding="utf8", errors="replace", creationflags=NO_CONSOLE)
    stages = len(scene["objects"]) + len(scene["coatings"]) + images
    last_lines, saved, warnings = [], 0, []
    with ui.progress(f"{what}: Blender starts", stages) as bar:
        for line in process.stdout:
            last_lines = (last_lines + [line.rstrip()])[-15:]
            event = blender_protocol.read(line.strip())            # None for other Blender output
            kind = event.get("event") if event else None
            if kind == "built":
                bar.advance(f"{what}: built {event.get('name', '')}")
            elif kind in ("device", "rendering"):
                bar.update(f"{what}: rendering image")
            elif kind == "saved view":
                saved += 1
                bar.advance(f"{what}: {saved} of {images} images done")
            elif kind == "saved" and str(event.get("file", "")).endswith(".png"):
                bar.advance(f"{what}: done")
            elif kind == "warning":
                warnings.append(event.get("text", ""))
    process.wait()
    for text in warnings:
        ui.warn(text)
    _blender = None
    if process.returncode != 0 or not os.path.exists(image_file):
        ui.note("\n".join(last_lines))
        raise answers.Stop("Blender stopped with an error. Last Blender lines are above.")
