"""
Step 5: put the labels on the render.

  1. Put the render (transparent background) on a white page, or on a transparent page (answer "background").
  2. Add a column on the right with one label for each layer: its name and its real thickness.
  3. Draw a thin line from each label to its layer (Blender gave one image point on each layer).
  4. Add the notes at the bottom (example: "Not to scale").

The result is 6_exploded_view.png.
"""
import json
import os

import matplotlib
matplotlib.use("Agg")                      # write image files only, open no window
import matplotlib.image as mpimg
import matplotlib.pyplot as plt

from backend import ui

LABEL_COLUMN = 0.42        # width of the label column, as a fraction of the render width
TEXT_COLOUR, LINE_COLOUR, NOTE_COLOUR = "#1d2430", "#5a6270", "#7a828e"


def spread(wanted, lowest, highest, gap):
    """Return label heights near the wanted heights, at least `gap` apart, between lowest and highest.
    The wanted heights must be sorted from the top of the image to the bottom."""
    placed = []
    for y in wanted:
        placed.append(max(y, lowest, placed[-1] + gap if placed else lowest))
    overflow = placed[-1] - highest if placed else 0
    if overflow > 0:                                 # too low: move the labels up, and keep the gaps
        placed = [y - overflow for y in placed]
        for i in range(len(placed) - 2, -1, -1):
            placed[i] = min(placed[i], placed[i + 1] - gap)
    return placed


def text_width(text, size, bold=False):
    """Width of a text in pixels, for a font size in points. The measure comes from the renderer that writes the
    final image (Agg, 100 pixels per inch), so it is the width of the drawn text."""
    from matplotlib.backends.backend_agg import RendererAgg
    from matplotlib.font_manager import FontProperties
    width, _, _ = RendererAgg(10, 10, 100).get_text_width_height_descent(
        text, FontProperties(size=size, weight="bold" if bold else "normal"), ismath=False)
    return width


def column_width(labels, size, image_width):
    """Width of the label column (pixels): LABEL_COLUMN x the image width, or more if a label needs more room.
    The text starts at 6 % of the column and keeps 2 % free on the right, so it is never cut."""
    widest = max((max(text_width(label["name"], size, bold=True), text_width(label["text"], 0.85 * size))
                  for label in labels), default=0)
    return max(int(LABEL_COLUMN * image_width), int(widest / 0.92) + 1)


def cut_empty_border(image, margin=0.04):
    """Cut the transparent border around the device, but keep a small margin.
    Return the cut image and the (x, y) shift of the image points."""
    rows = (image[:, :, 3] > 0.01).any(axis=1).nonzero()[0]
    cols = (image[:, :, 3] > 0.01).any(axis=0).nonzero()[0]
    if len(rows) == 0:
        return image, (0, 0)
    pad = int(margin * max(image.shape[:2]))
    top, bottom = max(rows[0] - pad, 0), min(rows[-1] + pad, image.shape[0])
    left, right = max(cols[0] - pad, 0), min(cols[-1] + pad, image.shape[1])
    return image[top:bottom, left:right], (left, top)


def run(scene, image_file, project_folder):
    """Do step 5. Return the file of the final image."""
    ui.header(5)
    with open(image_file[:-4] + "_points.json", encoding="utf8") as f:
        points = json.load(f)
    render = mpimg.imread(image_file)
    render, shift = cut_empty_border(render)
    for p in points["points"]:                        # the label points move with the cut
        p["xy"] = [p["xy"][0] - shift[0], p["xy"][1] - shift[1]]
    h, w = render.shape[:2]

    transparent = scene.get("background", "white") == "transparent"   # else: the white page
    page = "none" if transparent else "white"
    if scene.get("show labels", "yes") == "no":       # the user asked for an image with no text
        final = os.path.join(project_folder, "6_exploded_view.png")
        fig = plt.figure(figsize=(w / 100, h / 100), dpi=100)
        ax = fig.add_axes((0, 0, 1, 1))
        ax.axis("off")
        ax.imshow(render)
        fig.savefig(final, dpi=100, facecolor=page, transparent=transparent)
        plt.close(fig)
        ui.success("Exploded view ready (no labels).", os.path.abspath(final))
        return final

    size = 0.011 * points["resolution"][0]            # font size (points): the same for all views
    column = column_width(scene["labels"], size, w)   # wide enough for the longest label
    pixels = size * 100 / 72                          # the same size in pixels (1 point = 1/72 inch, 100 pixels/inch)
    gap = 2.6 * pixels                                # the distance between two labels

    # Make the page taller if the labels need more room than the image gives. Keep room for the notes.
    labels_room = len(scene["labels"]) * gap / 0.8
    extra_top = max(0, int((labels_room - h) / 2))
    page_h = h + 2 * extra_top + int(3 * pixels)

    notes = "   ".join(scene["notes"])
    page_w = max(w + column, int(text_width(notes, 0.7 * size) + 0.04 * w) + 1)   # the notes are never cut either
    fig = plt.figure(figsize=(page_w / 100, page_h / 100), dpi=100)
    ax = fig.add_axes((0, 0, 1, 1))
    ax.set_xlim(0, page_w)
    ax.set_ylim(page_h, 0)                            # y down, as in the image
    ax.axis("off")
    fig.patch.set_facecolor("white")
    ax.imshow(render, extent=(0, w, extra_top + h, extra_top))

    label_of = {label["anchor"]: label for label in scene["labels"]}
    anchors = sorted((p for p in points["points"] if p["index"] in label_of), key=lambda p: p["xy"][1])
    for p in anchors:
        p["xy"][1] += extra_top
    heights = spread([p["xy"][1] for p in anchors], 0.08 * page_h, 0.88 * page_h, gap)
    text_x = w + 0.06 * column
    # Elbow lines: first horizontal from the point to a common column right of all the points, then to the label.
    # Horizontal parts at different heights cannot cross, and the labels have the order of the points.
    elbow_x = min(max(p["xy"][0] for p in anchors) + 0.02 * w, text_x - 0.04 * column) if anchors else text_x
    for p, y in zip(anchors, heights):
        label = label_of[p["index"]]
        ax.plot([p["xy"][0], elbow_x, text_x - 0.03 * column], [p["xy"][1], p["xy"][1], y],
                color=LINE_COLOUR, linewidth=0.0014 * w)
        ax.plot(*p["xy"], "o", color=LINE_COLOUR, markersize=0.003 * w)   # the dot stays larger than the line
        ax.text(text_x, y, label["name"], color=TEXT_COLOUR, fontsize=size, fontweight="bold", va="bottom")
        ax.text(text_x, y, label["text"], color=NOTE_COLOUR, fontsize=0.85 * size, va="top")

    ax.text(0.02 * w, page_h - 0.8 * pixels, notes, color=NOTE_COLOUR, fontsize=0.7 * size, va="bottom")
    final = os.path.join(project_folder, "6_exploded_view.png")
    fig.savefig(final, dpi=100, facecolor=page, transparent=transparent)
    plt.close(fig)
    ui.success("Exploded view ready.", os.path.abspath(final))
    return final
