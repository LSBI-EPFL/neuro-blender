# Tests

## Run the tests

```
cd <path of the neuro-blender folder>
conda activate neuro-blender
python tests/run_all.py
```

- `python tests/run_all.py` runs the tests that need no screen and no Blender.
- `python tests/run_all.py --all` also runs the window test and the image test.
- The exit code is 0 only if all the tests pass.

## The test files

| File | What it tests | Needs |
|---|---|---|
| `tests/test_backend.py` | The logic of the back end: steps, answers, navigation, geometry, forms (with test front ends). | Nothing |
| `tests/test_questions.py` | The terminal questions, with simulated key presses. | Nothing |
| `tests/test_window.py` | The window questions and forms, with simulated keys and clicks. The window opens for some seconds. | A screen |
| `tests/test_render.py` | Renders the test design and compares it with `tests/reference/linear_probe_render.png`. | Blender 5.0, about 10 s |

## The image test

`tests/test_render.py` renders the test design at test quality (640 x 360) and compares it with the reference image.
The test fails when more than 0.2 % of the pixels have a difference of more than 0.1. Two renders on one computer
are almost the same, so a small change of the geometry or the look makes the test fail.

When you change the look on purpose:
1. Look at the new render and make sure that it is correct.
2. Run `python tests/test_render.py --update` to save it as the new reference.
3. Commit the new reference image with the change.

## Images of the window

`python tests/test_window.py --screenshots <folder>` saves an image of each question. `tests/window_drawing.py`
draws each image from the widget data of the window. It does not capture the screen, so it never shows other
windows. The fonts and some widgets are simple shapes: the images show the layout, not an exact copy.

## How to check a change

1. Run `python tests/run_all.py`.
2. For a change of the questions: compare the questions and the default answers before and after the change, in
   the terminal and in the window.
3. For a change of the window: draw it with `tests/window_drawing.py` and look at the image.
4. For a change of the geometry or the look: run `python tests/test_render.py`.
5. After a test run: make sure that `tests/design/linear_probe_stack.yaml` did not change.

## The test design

`tests/design/` holds the test design: a linear probe, drawn only for the tests. It is not a real device.
- `make_linear_probe.py` draws it again: `python tests/design/make_linear_probe.py`.
- `linear_probe.dxf` is the mask file.
- `linear_probe_stack.yaml` holds the answers.

The probe has a straight shank with 8 electrodes in one vertical column, 4 tracks on each side of the column and 8
pads on a wide base. The stack has PDMS and PI layers, Ti/Au tracks and a Pt coating on the electrodes.

If you change the test design, save a new reference image with `python tests/test_render.py --update`.
