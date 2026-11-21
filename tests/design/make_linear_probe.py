"""
Make the test design: a simple linear probe, drawn only to test Neuro Blender. It is not a real device.

Run:  python tests/design/make_linear_probe.py
It writes tests/design/linear_probe.dxf (unit: µm). The device has:
  - a straight shank (600 µm wide, pointed tip) with 8 electrodes in one vertical column (diameter 120 µm,
    pitch 300 µm);
  - 4 tracks on each side of the column. The top electrode uses the outer lane, so the tracks do not cross;
  - a wide base with 8 pads in one row.
The answers for this design are in tests/design/linear_probe_stack.yaml: PDMS and PI layers, gold tracks and a
platinum coating on the electrodes.

DXF layers:
  OUTLINE               the shape of the device
  METAL                 the tracks (each track = electrode disc + line + pad)
  OPENINGS_ELECTRODES   the openings in the top layers over the electrodes
  OPENINGS_PADS         the openings in the top layers over the pads
  COATING               the electrode coating (over the electrodes only)
"""
import os

import ezdxf
from shapely.geometry import LineString, Point, Polygon, box
from shapely.ops import unary_union

HERE = os.path.dirname(os.path.abspath(__file__))

# The outline (µm): base (pads), taper, shank, pointed tip.
outline = Polygon([(-1500, 0), (1500, 0), (1500, 2000), (300, 2800), (300, 5700), (0, 6200), (-300, 5700),
                   (-300, 2800), (-1500, 2000)]).buffer(-20).buffer(20)          # round corners

ELECTRODES_Y = [5500 - 300 * i for i in range(8)]  # the 8 electrodes, top to bottom, all at x = 0
DIAMETER, METAL_RIM, TRACK_WIDTH = 120, 10, 10
LANES = [220, 180, 140, 100]                       # distance of the lanes from the column, outer lane first

lanes = []                                         # (x of the lane, y of the electrode)
for i, y in enumerate(ELECTRODES_Y):
    side = -1 if i % 2 == 0 else 1                 # electrodes 1, 3, 5, 7 to the left; 2, 4, 6, 8 to the right
    lanes.append((side * LANES[i // 2], y))
lanes.sort()                                       # left to right: the order of the pads

tracks, electrode_openings, pad_openings = [], [], []
for i, (lane_x, y) in enumerate(lanes):
    pad_x = -1225 + 350 * i                        # the 8 pads, 350 µm apart
    pad = box(pad_x - 125, 250, pad_x + 125, 950)
    path = LineString([(0, y), (lane_x, y), (lane_x, 2800), (pad_x, 1900), (pad_x, 950)])
    tracks.append(unary_union([path.buffer(TRACK_WIDTH / 2), Point(0, y).buffer(DIAMETER / 2 + METAL_RIM), pad]))
    electrode_openings.append(Point(0, y).buffer(DIAMETER / 2, quad_segs=32))
    pad_openings.append(pad.buffer(-40))


def add(msp, polygon, layer):
    """Add the outer line of a polygon as one closed polyline."""
    msp.add_lwpolyline(list(polygon.exterior.coords), close=True, dxfattribs={"layer": layer})


doc = ezdxf.new()
doc.header["$INSUNITS"] = 13                       # 13 = micrometre
msp = doc.modelspace()
add(msp, outline, "OUTLINE")
for track in tracks:
    add(msp, track, "METAL")
for site in electrode_openings:
    add(msp, site, "OPENINGS_ELECTRODES")
    add(msp, site, "COATING")
for pad in pad_openings:
    add(msp, pad, "OPENINGS_PADS")
doc.saveas(os.path.join(HERE, "linear_probe.dxf"))
print("Wrote tests/design/linear_probe.dxf")
