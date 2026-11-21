# Neuro Blender: the manual

Neuro Blender is a tool that makes an exploded-view image of a thin-film implant. It uses the mask file of the
implant (DXF or GDS) and your answers to a series of questions. Blender (a free 3D program) renders the image.

The image shows:
- **Tracks:** the metal lines. They stay flat.
- **Encapsulation layers:** the polymer layers (PI, PDMS, parylene). A cleaved encapsulation layer bends away from
  the tracks. Layers below the tracks bend down. Layers above the tracks bend up.
- **Electrode coatings:** the materials on the electrodes. They float above the electrodes. Dashed lines can connect
  the electrodes to their coatings: on all the electrodes, on some of them, or on none.
- **Labels:** the name and the real thickness of each layer.

The image is not to scale. The tool draws the thicknesses and the gaps larger, so that you can see them.

## Terms

| Term | Meaning |
|---|---|
| Mask file | The drawing of the photolithography masks: a DXF file or a GDS file. |
| Mask layer | One layer of the mask file. In a GDS file, a mask layer has a number: `1/0` is layer 1, datatype 0. You give it a name in step 1. |
| Stack | The layers of the device, from the bottom to the top. |
| Terminal | The text window where you type commands. On Windows, use the "Anaconda Prompt". |
| Window (GUI) | The graphical user interface of the tool: a window with buttons and images. |
| TUI | The text user interface of the tool: the same questions, in the terminal. |
| Conda environment | A separate Python installation with the packages that the tool needs. Its name is `neuro-blender`. |
| Render | The calculation of the image by Blender. |

## Requirements

- **Anaconda or Miniconda:** this installs Python and the packages. Download it from [anaconda.com](https://www.anaconda.com).
- **Blender:** download it free from [blender.org](https://www.blender.org). The tool is tested with Blender 5.0.
- **Graphics card (optional):** with a graphics card, a final image takes approximately 1 minute. Without one, it
  can take up to 20 minutes.

The tool is tested on Windows.

## Install (one time)

Open the terminal and type these commands. Replace `<folder>` with the full path of the neuro-blender folder.

```
cd "<folder>"
conda env create -f environment.yml
```

After you get a new version of the tool, update the environment:

```
cd "<folder>"
conda activate neuro-blender
conda env update -f environment.yml
```

## Check the installation (optional)

These tests need no mask file and no Blender. Each line shows PASS or FAIL, and the last lines show one result.

```
cd "<folder>"
conda activate neuro-blender
python tests/run_all.py
```

`python tests/run_all.py --all` also runs the window test (it opens windows for some seconds) and the image
regression test (it needs Blender, about 10 s). The image test compares a render of the test design
(`tests/design/`) with `tests/reference/linear_probe_render.png`. The reference belongs to one computer: on a new computer, look at a render
first, then save it as the reference with `python tests/test_render.py --update`.

## Start the tool

To open the window with a double-click, use the start file in the neuro-blender folder:
`Neuro Blender (Windows).bat` on Windows, `Neuro Blender (Mac).command` on a Mac. On a Mac, the first start can be
blocked by macOS: right-click the file, then select **Open**.

To open the window (GUI) from the terminal:

```
cd "<folder>"
conda activate neuro-blender
python main.py
```

To get the same questions in the terminal (TUI):

```
cd "<folder>"
conda activate neuro-blender
python main.py --terminal
```

The window and the terminal ask the same questions, in the same order, and they save the same answers.
You can start with one and continue with the other.

The first question asks for your mask file:
- If the folder `my_designs` contains mask files, a list shows them.
- The list always has the choice "Find the file in a window ...". Select it to find your file anywhere.

## The window

| Part | Content |
|---|---|
| Left | The 5 steps. The current step is red. Dark red steps have answers: click one to see and change its answers (see "Going to a step" below). |
| Middle, top | The messages: notes, tables, your stack and your previous answers. In step 3 and in step 4 (before the 3D build), a form takes this place: all the questions of the step together. |
| Middle, bottom | The question. Click your answer, then click **Next**. **Back** returns to the previous question (see "Going back" below). In a form, **Next** checks all the values; a wrong value shows in red under its field. |
| Right | The images: the layers, the devices, the stack, the test views and the final image. Use **<** and **>** to see all the images of a folder. In a question about a mask layer, the image of the selected mask layer shows. |
| Bottom | The progress bar: what the tool does now. |

Keys in the window: Enter = Next, Esc = Back, ↑ ↓ = move in a list, Space = tick a box, Y / N = yes / no.

For a colour, type a name or a hex code, or click **Colour window ...** to select the colour and its transparency.

At the end, the window shows your image and 4 buttons: **Start again** (the same mask file), **Open image**,
**Open folder** and **Close**. Click a step on the left to change its answers and render again. If you close the
window during a render, Blender stops too.

## Keys in the terminal

| Key | Action |
|---|---|
| ↑ ↓ | Move in a list. The grey line under the list explains the selected choice. |
| Enter | Confirm the answer. |
| Space | Tick or untick a box (questions with more than one answer). Tick at least one box: Enter with no tick is refused. |
| Esc | Return to the previous question (see "Going back" below). |
| F1 to F5 | Go to step 1 to 5 (see "Going to a step" below). |
| Ctrl+C | Stop the tool. Your answers stay saved. |

A bar at the top of the terminal shows the 5 steps and your current step.

Some terminals cannot show the lists (for example, the console of a code editor). In these terminals, type the
number of the answer and push Enter. Type `b` to return to the previous question, or `s1` to `s5` to go to a step.

## Going to a step

Click a step in the window (left), or push F1 to F5 in the terminal:
- The questions of that step come again. Your old answers are the default answers: push Enter (or Next) to keep
  an answer.
- The later steps keep their answers. They ask only the questions that have no answer.
- Step 1 (File) goes to the start: the question about your saved answers.
- A later step is possible when it has saved answers: the steps before it keep their answers.
- In the window, this is also possible at the start (the question about your saved answers) and at the end: then a
  new run opens that step with your saved answers.

## Going back

Esc (in the terminal) and **Back** (in the window) work the same:
- Back goes to the previous question that you answered in this run, also in an earlier step. Your old answer is
  the default answer: push Enter (or Next) to keep it.
- Before the first question of the steps, Back goes to the start: the question about your saved answers, and then
  the question about the mask file. So you can go back all the way to the start.
- Going back never deletes an answer from `stack.yaml`.

## The 5 steps

### Step 1: read the mask file

The tool reads all the mask layers. A table shows the number of shapes and the size of each mask layer.
The folder `1_all_layers` gets one image of each mask layer. Use these images to identify a mask layer by its shape.

If a DXF file does not give its unit, the tool asks for it: nm, µm, mm or cm. A DXF file with another unit (for
example metre or inch, often a default value of the drawing program) counts as a file with no unit. A GDS file
always gives its unit.

A GDS file has no layer names, only numbers. For a GDS file, the tool asks for a name for each layer:
1. The image `1_layer_overview.png` shows all the layers, each with its number and its shapes. The window shows
   it on the right. The terminal opens it in your image program.
2. Type a name for each layer (example: `4/0` → `outline`). To keep the number, accept the default answer
   (Enter in the terminal, Next in the window).
3. All the next questions and images use your names. The tool asks for the names one time only.

If a KLayout layer file with the same name (`<name of the GDS file>.lyp`) is in the same folder, the tool reads
the names from it. Accept the default answer to keep each name.

### Step 2: select the device

1. Select the mask layer that draws the outline of the device.
2. If the mask file contains more than one device (a full wafer), select the device number.
   The image `2_device_numbers.png` shows the number of each device.
3. Tick the mask layers that draw the **through holes**: holes through all the layers of the device. An example is
   suture holes. The surgeon puts a suture through them to hold the implant in its position. If the device has no
   through holes, keep the tick on `no through holes`.

### Step 3: build the stack

Describe the layers from the bottom to the top, in the order of your process. A layer is one mask shape with
one type. A layer can have more than one material. Example: tracks of Ti, Pt and Ti are one layer with 3 materials.

The tool asks these questions for each layer:

| Question | Answer |
|---|---|
| Name | The text of the label. Example: `Top PI`. |
| Type | `encapsulation` (a polymer layer), `tracks` (the metal lines) or `electrode coating` (material on the electrodes only). |
| Shape | The mask layer that draws this layer. More than one layer can use the same mask layer. |
| Materials | Each material and its real thickness, from the bottom up, with a comma between two materials. Example: `Ti 25 nm, Pt 150 nm, Ti 25 nm`. One material: `PI 3 um`. |
| Colours | One colour for each different material. Type a colour name (`gold`) or a hex code (`#e3b04b`). Add a percentage for a transparent colour: `#e3b04b 40%`. Or open the colour window (the button **Colour window ...** in the window, `p` in the terminal) and select the colour and its transparency (0 % = solid, 90 % = almost clear). |
| Openings | Encapsulation only. Tick the mask layers that draw the openings in this layer, for example the electrode openings and the pad openings. If the layer has no openings, tick `no openings`. The tool does not accept an answer with no tick. |
| Cleave | Encapsulation only. `yes` = the layer bends away from the tracks in the image. |
| Surface | Tracks and coatings only. `shiny` (like a metal) or `matte` (no shine). |

After each layer, the tool shows a drawing of the stack in your colours.

In the window, step 3 is one form: one line for each layer, top layer first. Click a line to open its values,
change a value, then click **Next**. **+ Add a layer on top** adds a layer with the values of the layer under it as
defaults. The drawing of the stack on the right changes at once and marks the open layer in red.

Rules for the stack:
- The stack must have at least one tracks layer.
- All the tracks layers must be one after the other.
- The electrode coatings must be above the tracks.

### Step 4: render the image

1. If the stack has no electrode coating and the openings come from more than one mask layer, select the mask
   layers of the electrode openings (not the contact pad openings). The tool turns the device so that the electrodes
   are at the far end.
2. Select the part of the device to show: the electrodes (a zoom on the electrode end) or the whole device.
3. If some electrodes are much smaller than the others, select if the tool draws them 2 times larger.
4. Type the cleave angle (only if a layer is cleaved): the angle in degrees between two cleaved layers next to
   each other. `0` = no cleave: all the layers stay flat, one above the other.
5. Type the space between the layers, in image units. The image is not to scale, so the tool uses its own unit:
   the thickest layer in the image is 10 units thick. The question gives the thickness of each of your layers in
   this unit (example: "Bottom PDMS 10, Bottom PI 5, Metallization 3"). `0` = the layers touch. With a cleave, the
   default is `0`. With no cleave, the default is `30` (a flat exploded view).
   For a stack with an electrode coating, also type the distance from the device to the coatings, in the same
   image units. `0` = the coatings touch the top layer. The default is `20`.
6. Select the view. The tool first renders a small test image of your device from 4 views. The image
   `5_view_choices.png` shows them:

   | View | What you see |
   |---|---|
   | 1 Front, low | The eye is a little above the device. You see into the cleave and the tracks. |
   | 2 Front, high | You look down on the device. You see the openings and the top layer. |
   | 3 Side | You look from the side. The cleave shows as a V shape. |
   | 4 From the tip | The tip points to you. You see the electrodes from the front. |
   | 5 My own angles | You type 2 angles in degrees. Turn: 0 = from the side, 90 = from the tip, 180 = from the other side. Height: 0 = eye level, 90 = from directly above. |

7. Select the dashed lines (only for a stack with an electrode coating). A dashed line goes from each electrode,
   through its opening, to its coating. The tool first renders a small test image for each choice, from your view.
   The image `5_guide_choices.png` shows them:

   | Choice | What you see |
   |---|---|
   | All the dashed lines | One line for each electrode. Clear for a device with few electrodes. |
   | Some dashed lines | Lines on 6 electrodes only, spread over the device (only for more than 6 electrodes). Clear for a device with many electrodes. This is the default for more than 6 electrodes. |
   | No dashed lines | Only the device and the coatings. |

8. Show the labels? No = an image with no text.
9. Select the image quality: `preview` (1280 × 720 pixels) or `final` (2560 × 1440 pixels).

How the tool draws the layers:
- The encapsulation layer directly on the tracks fills the space around the tracks, down to the layer under the
  tracks. The tool finds this space from the mask file: the distance between the outline of the layer and the
  tracks. So, at the edge of the device, the two encapsulation layers touch, and the tracks are inside them, as in
  the real device. With a space between the layers, the underside of this layer shows the shape of the tracks.
- All the edges are round (a fillet). The radius is half the drawn thickness of the layer. On a narrow shape, the
  radius is smaller, so that the rounded edges of the two sides do not cross.

### Step 5: add the labels

The tool adds the labels and saves the final image. The window shows the image on the right, with the buttons
**Open image** and **Open folder**. The terminal shows the path of the image in a box with a blue-green
border.

## Next run with the same mask file

The tool saves your answers. At the next run with the same mask file, a list shows 3 choices (in the window: 2
choices; click a step to change its answers):

| Choice | Result |
|---|---|
| Render again with saved answers | The tool asks only for the image quality. |
| Change one part: device, stack or view | The tool asks only the questions of that part. Your old answers are the default answers: push Enter (or Next) to keep an answer. For the stack, select one layer, "New layer on top" or "Full stack again". |
| Start new answers | The tool asks all the questions again. It keeps a copy of the old answers. |

## Results

The tool puts all the results in the folder `projects/<name of your mask file>/`:

| File | Content |
|---|---|
| `6_exploded_view.png` | **The final image, with the labels.** |
| `5_render.png` | The render without labels, on a transparent background. |
| `5_render.blend` | The Blender scene. Open it in Blender to change the camera, a colour or the light by hand. |
| `5_view_choices.png` | The 4 test views of step 4. |
| `5_guide_choices.png` | The test images of the dashed lines (step 4). |
| `4_stack.png` | A drawing of the stack. The heights are not to scale. |
| `3_device_layers/` | One image of each mask layer of your device. |
| `2_device_numbers.png` | The number of each device (only for a mask file with more than one device). |
| `1_all_layers/` | One image of each mask layer of the full mask file. |
| `1_layer_overview.png` | All the layers in one image (only for a GDS file). |
| `stack.yaml` | Your answers. |

## The answers file (`stack.yaml`)

`stack.yaml` is a text file in YAML format. It has 3 parts:

```yaml
format: 2                   # the format of the file (the tool converts older files)
design:                     # the device
  outline layer: OUTLINE
  device number: 1
  through holes: [THROUGH_HOLES]
layers:                     # the stack, from the bottom up
- name: Tracks
  type: tracks
  shape: METAL
  materials:
  - {material: Ti, thickness: 20 nm, colour: '#8c857b'}
  - {material: Au, thickness: 200 nm, colour: '#e3b04b'}
  surface: shiny
render:                     # the view
  view: electrodes
  guide lines: all
  labels: true
  cleave angle: 9
  space between layers: 0
  coating distance: 20
  camera:
    turn: 32
    height: 11
```

You can change `stack.yaml` with a text editor:
- Change a value, and the next run uses the new value.
- Remove a value, and the next run asks that question again.
- Keep the quotes around the colours (`'#8c857b'`). In YAML, a `#` without quotes starts a comment.
- If the file has an error, the tool stops with the line number of the error.
- A transparent colour has one more value: `{material: PI, thickness: 5 um, colour: '#d99a2b', transparency: 40%}`.

To give your answers to another person with your mask file:
1. Copy `stack.yaml` into the folder of the mask file.
2. Give it the name `<name of the mask file>_stack.yaml`.

At the first run with that mask file, the tool asks if it can use these answers. The file does not contain the
location of your mask file: it is safe to share.

## Privacy

Git (the version control program of the repository) ignores the folders `my_designs/` and `projects/`.
Your mask files and your results do not go into the repository.

## Folder map

The tool has one back end and two front ends. The back end has all the logic: what to ask, how to check an
answer, the 3D scene, Blender and the labels. A front end only shows the questions and the results, and it
gives the answers to the back end. All the messages between them go through `backend/ui.py`.

```
README.md                     the front page of the repository: what the tool is, and how to start it
main.py                       the file that you run (the window, or the terminal with --terminal)
Neuro Blender (Windows).bat   double-click start on Windows: activates the conda environment, opens the window
Neuro Blender (Mac).command   double-click start on a Mac: the same
environment.yml               the packages for the conda environment
requirements.txt              the same packages, for pip (without conda)
backend/                      all the logic
  flow.py                     the order of the work: the mask file, the saved answers, the 5 steps, going back
  run_cache.py                the results that one run keeps (going back is fast); cleared at each run
  questions.py                questions as data: key, kind, text, default, check, condition (both front ends)
  ui.py                       the link to the front end: the list of all the questions and messages
  answers.py                  the answers: saving, the return to a previous question, the stack.yaml file
  step1_read_mask.py          step 1: read the mask file (DXF or GDS)
  step2_pick_device.py        step 2: select the device
  step3_layer_questions.py    step 3: build the stack
  step4_build_scene.py        step 4: make the 3D scene and start Blender
  blender_runner.py           step 4: find Blender, check its version, run it, stop it
  blender_protocol.py         the agreement with the Blender script: scene format, progress lines
  blender_render.py           step 4: the part that runs inside Blender
  step5_labels.py             step 5: add the labels
frontends/                    the display only
  window.py                   the window (GUI), made with Tkinter
  terminal.py                 the terminal (TUI), made with rich and questionary
  colour_window.py            the colour window: colour and transparency (both front ends)
  stack_form.py               the window: step 3 as one form (one card for each layer) and the stack drawing
  forms.py                    the window: the fields of the forms, and the page form (step 4 before the 3D build)
  theme.py                    the colours (EPFL graphic charter), the colour mix and the font (both front ends)
  desktop.py                  sharp windows with display scaling; open a file in its usual program (both front ends)
examples/                     other designs (not in the published repository)
tests/
  design/                     the test design: a linear probe drawn only for the tests (make_linear_probe.py, the
                              mask file and its answers)
  test_questions.py           tests the terminal questions with simulated keys: python tests/test_questions.py
  test_window.py              tests the window questions with simulated keys and clicks: python tests/test_window.py
  test_backend.py             tests the logic of the back end (no window, no Blender): python tests/test_backend.py
  test_render.py              renders the test design and compares it with reference/linear_probe_render.png (needs Blender)
  run_all.py                  runs all the tests and shows one result: python tests/run_all.py (--all: also window, image)
  window_drawing.py           draws a window into an image from its widgets (no screen capture), for test_window.py
docs/                         the documents: this manual
  public/                     the guides for developers who change the code
  private/                    notes that stay on your computer (not in the published repository)
my_designs/                   put your mask files here (optional; the tool makes this folder)
projects/                     your results (the tool makes this folder)
```

## Change the look

The values that control the look are at the top of these files:

| File | Value | Controls |
|---|---|---|
| `backend/step4_build_scene.py` | `LOOK` | Drawn thicknesses (and their limit for narrow features), the default cleave angle and space, gaps between the coatings, the radius of the rounded edges. |
| `backend/step4_build_scene.py` | `SOME_GUIDES` | The number of dashed lines for the choice "Some dashed lines" (6). |
| `frontends/theme.py` | `RED`, `GROSEILLE`, `LEMAN`, `PERLE` and the greys | The colours of the window and the terminal (the colours of the EPFL graphic charter). |
| `backend/step4_build_scene.py` | `VIEWS` | The camera angles of the 4 views. |
| `backend/blender_render.py` | `LENS` | The camera lens. |
| `backend/blender_render.py` | `QUALITY` | The image sizes and the render samples. |

## Limits

- In a DXF file, the shapes must be closed lines. The tool does not use open lines. Step 1 shows the number of open lines of each mask layer.
- The image is not to scale. A note on the image says this. The drawn thicknesses keep the order of the real
  layer thicknesses (on a log scale): a thin metal layer is never drawn thicker than a thick polymer layer.
  Each material of a layer gets at least 20 % of the drawn thickness of the layer, so that thin films stay visible.
- The drawn thickness of a layer is never more than 0.35 times the typical width of the device features, so that
  narrow features (for example a mesh) stay flat.
- GDS writers cut a polygon with many points into pieces. The tool joins the pieces that touch, so a device outline
  stays one shape. As a result, two shapes of one mask layer that touch become one shape.
- If a stack has no electrode coating, and one mask layer draws the electrode openings and the contact pad openings
  together, the tool cannot separate them. The device can then point the wrong way.
