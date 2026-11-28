# Architecture

## One back end, two front ends

| Part | Files | Job |
|---|---|---|
| Back end | `backend/` | All the logic: the steps, the questions, the checks, the answers, the geometry, Blender. |
| Link | `backend/ui.py` | The only link between the back end and a front end. |
| Window (GUI) | `frontends/window.py`, `forms.py`, `stack_form.py`, `colour_window.py` | Shows the messages and the questions with Tkinter. |
| Terminal (TUI) | `frontends/terminal.py` | Shows the same messages and questions with rich and questionary. |
| Start | `main.py` | Selects the front end with `ui.use()` and starts `flow.run()`. |
| Double-click start | `Neuro Blender (Windows).bat`, `Neuro Blender (Mac).command` | Find conda, activate the environment `neuro-blender`, run `main.py`. The Windows file uses `pythonw` (no terminal window), so the window code must not write to the terminal. |

The main rule: a front end has no logic. It shows what the back end sends and returns the answer. A new question,
default answer, check or calculation goes into the back end. Both front ends then get it with no change.

`frontends/theme.py` holds the colours and the font of both front ends. `frontends/desktop.py` holds two actions on
the computer: sharp windows with display scaling, and open a file in its usual program.

## The order of the work

`backend/flow.py` runs the work: it selects the mask file, reads the saved answers, then runs the 5 steps in order.
Each step uses the results of the steps before it.

| Step | File | What it does | Result files |
|---|---|---|---|
| 1 File | `step1_read_mask.py` | Reads the mask file, finds its unit, names the mask layers. | `1_layer_overview.png` |
| 2 Device | `step2_pick_device.py` | Selects the outline layer, the device and the through holes. | `2_device_numbers.png` |
| 3 Stack | `step3_layer_questions.py` | Builds the layers of the device from the bottom up. | `4_stack.png` |
| 4 Render | `step4_build_scene.py` | Makes the 3D values, the test views and the scene file, then runs Blender. | `5_view_choices.png`, `5_view_angles.png`, `5_scene.json`, `5_render.png` |
| 5 Labels | `step5_labels.py` | Puts the name and thickness of each layer on the render. | `6_exploded_view.png` |

`ui.STEPS` is the only list of the steps. The results go into `projects/<name of the mask file>/`.

The result files are the names that start with `1_` to `6_` (`flow.RESULT_NAME`). Before the start question,
`flow.keep_or_archive()` asks to move old result files to `archive/<date and time>/` or to overwrite them. At the
end of the run, `flow.remove_unkept()` deletes the kinds of result files that the answer `render keep files` does
not have. The tool never moves or deletes other files in the folder.

## The answers

- The answers are one flat dictionary of texts, with one key for each answer. Example:
  `"layer 2 materials": "Ti 25 nm, Pt 150 nm"`.
- `backend/answers.py` reads and writes the answers file `stack.yaml` (with a format version and a safe write).
  It also reads the answer texts: materials, thicknesses, layer lists, colours.
- `answers.answer()` returns a saved answer, or asks the question and saves the new answer.
- `answers.remembered_colours()` and `answers.remember_colours()` read and write `projects/material_colours.yaml`:
  the last colour of each material, for all designs. Step 3 uses it as the default colour of a material that has no
  colour in a layer below.
- `flow.step_of(key)` gives the step that asks each key.

## Questions as data

`backend/questions.py` holds the `Question` class: key, kind, text, help, options, default answer, check, the
condition that makes it necessary, and a short label. A step writes each question one time. The kinds are text,
choice, yes/no, layer, layers, number, materials and colours.

The same `Question` objects serve both front ends:
- The terminal asks one question at a time (`answer_all()`).
- The window shows a form when `ui.shows_forms()` is true:
  - Step 3: `ui.edit_stack()` opens `frontends/stack_form.py`, with one card for each layer.
  - Step 4: `answer_page()` calls `ui.ask_page()`, which opens `PageForm` in `frontends/forms.py`.
- Steps 1 and 2 ask one question at a time in both front ends, because each question needs the result of the
  question before it.

## Navigation

The back end raises three exceptions (in `backend/answers.py`):

| Exception | Cause | Result |
|---|---|---|
| `GoBack` | Esc, or the Back button | The last question of this run comes again. `answers.HISTORY` holds the order. |
| `GoToStep` | A click on a step or "Change some answers" at the start (window, `flow.choose_step`), or F1 to F5 (terminal) | The answers of that step and of the later steps move to `answers.PREVIOUS` and become the default answers (`flow.asked_again`; the terminal keeps step 3 unless the target is step 3). |
| `Stop` | A problem that ends the run | The front end shows the message. |

A later step can open when it has saved answers. If the user stops during a change, `flow.keep_old_answers()` keeps
the old answers in `stack.yaml`.

## The window and its thread

The back end runs in a separate thread. `frontends/window.py` gets each message and question through a queue
(`App.poll()`), and the back end waits for the reply. All Tk calls stay in the main thread.

`ui.ask_file()` is a list question that also takes a file dropped on the window (the mask file question). Its
option `browse` (the choice that opens the file window) shows in the window as a drop box above the list, and not
in the list. The window uses the package tkinterdnd2 for the drop. Without tkinterdnd2, the window works with no drop. The terminal
asks the same list with no drop.

## Blender

| File | Job |
|---|---|
| `backend/blender_runner.py` | Finds Blender, checks its version, runs it, stops it. |
| `backend/blender_protocol.py` | The agreement between both sides: the scene format version, the scene keys, and the progress lines (`NEURO_BLENDER {json}`). Both sides import it. |
| `backend/blender_render.py` | Runs inside Blender. It reads `5_scene.json` and writes the render. Do not run it yourself. |

## Results kept in one run

`backend/run_cache.py` keeps the results of one run (shapes, layer images, device map, 3D scenes, test renders), so
that going back is fast. The results stay for the next run with the same mask file (**Start again**). At the start
of each run, `flow.run()` calls `run_cache.use_mask_file()`: another file, or a change of the file on disk
(modification time or size), clears all the results.

A change of a look value (`LOOK_ONLY` in `step4_build_scene.py`: colour, transparency, surface) does not make a new
3D scene. `paint()` puts the new look on the kept scene.

## The look values

The values that control the look are at the top of these files: `LOOK`, `VIEWS` and `SOME_GUIDES` in
`backend/step4_build_scene.py`; `LENS` and `QUALITY` in `backend/blender_render.py`; the colours in
`frontends/theme.py`. The manual describes each value (section "Change the look").

## Folders

| Folder | Contents | In the repository |
|---|---|---|
| `backend/`, `frontends/` | The code. | Yes |
| `tests/` | The tests, the test design (`tests/design/`) and the reference image. | Yes |
| `examples/` | Other designs and their answers. | No |
| `docs/` | The manual and these guides. `docs/private/` stays on the computer of the owner. | Yes, but not `docs/private/` |
| `my_designs/` | The mask files of the user. | No |
| `projects/` | The results and the answers of the user. | No |
