"""
The order of the work. Both front ends (the window and the terminal) run it with flow.run().

  1. Select the mask file (DXF or GDS): a file in my_designs, or a window to find it.
  2. If saved answers exist for this design: render again, change one part, or start new answers.
  3. Do the 5 steps, in order.

Going to a step (a click on the step list of the window, or F1 to F5 in the terminal): the questions of that step
come again, with the old answers as default answers. Step 1 (File) = the start. A later step is possible when it has
saved answers: the steps before it keep their answers. In the window, a click on a step is the one way to change
answers (also at the start and at the end); the terminal also has "change one part".

Going back (Esc, or the Back button of the window) works the same in both front ends:
  - in the steps: back to the last question that the user answered in this run, also in an earlier step.
    The old answer is the default answer of that question.
  - before the first question of the steps: back to the start (the saved answers question), then to the mask file
    question. So Esc again and again goes back all the way to the start.

The results go into "projects/<name of the mask file>/". The answers go into stack.yaml in that folder.
"""
import hashlib
import os
import shutil
import time

from backend import answers, blender_runner, run_cache, step1_read_mask, step2_pick_device, step3_layer_questions, step4_build_scene, step5_labels, ui

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DESIGNS = os.path.join(REPO, "my_designs")
PROJECTS = os.path.join(REPO, "projects")
WINDOW = "find in a window"         # the choice that opens the "open file" window


class BackToStart(Exception):
    """The user went back from the first question of the steps: show the start questions again."""


def step_of(key):
    """The step (1 to 5) that asks this answer. 0 = no step (example: the mask file)."""
    if key in ("unit", "layer names"):
        return 1
    if key in ("outline layer", "device number", "through holes"):
        return 2
    if key.startswith("layer "):
        return 3
    if key.startswith("render "):
        return 4
    return 0
LAST_MASK_FILE = None               # the mask file of the last run (the window can start again with it)


def choose_mask_file():
    """Ask for the mask file: a file in my_designs, or the choice "Find the file in a window".
    The window never opens before the user selects this choice."""
    endings = (".dxf",) + step1_read_mask.GDS_ENDINGS
    os.makedirs(DESIGNS, exist_ok=True)                   # the folder for the mask files of the user
    designs = sorted(f for f in os.listdir(DESIGNS) if f.lower().endswith(endings))
    options = {name: name for name in designs}
    options[WINDOW] = "Find the file in a window ..."
    details = {WINDOW: "Opens a window to find the file anywhere."}
    if not designs:
        details[WINDOW] += " Tip: put mask files in folder my_designs to list them here."
    while True:
        choice = ui.ask_choice("Which mask file do you want to use?", "", options,
                               default=designs[0] if designs else WINDOW, details=details)
        if choice != WINDOW:
            return os.path.join(DESIGNS, choice)
        file = ui.pick_file("Select mask file", DESIGNS,
                            [("Mask file (DXF or GDS)", "*.dxf *.gds *.gds2 *.gdsii"), ("All files", "*.*")])
        if file:
            return os.path.abspath(file)
        ui.note("No file selected.")


def same_file(a, b):
    """True if two paths name the same file (Windows: case is not important)."""
    return os.path.normcase(os.path.abspath(a)) == os.path.normcase(os.path.abspath(b))


def project_owner(folder):
    """The mask file of a project folder, or None (a new folder, or an old project with no record).
    The file mask_file.txt keeps the full path. It stays on this computer: it is never in a shared answers file."""
    record = os.path.join(folder, "mask_file.txt")
    if os.path.exists(record):
        return open(record, encoding="utf8").read().strip() or None
    stack_file = os.path.join(folder, "stack.yaml")
    if os.path.exists(stack_file):                        # a project from before mask_file.txt
        return answers.read_stack(stack_file).get("dxf file")
    return None


def project_folder_for(mask_file):
    """The project folder of a mask file: projects/<name of the file>.

    Another mask file with the same name (example: implant.dxf and implant.gds, or one name in two folders): only
    the user knows if it is the same design (example: a copy). The tool asks. Yes = use that project. No = a new
    folder with a short code from the full path (example: implant_3f9a2c). A project whose mask file does not exist
    any more (the file was moved) goes to the moved file with no question."""
    base = os.path.splitext(os.path.basename(mask_file))[0]
    code = hashlib.sha1(os.path.normcase(os.path.abspath(mask_file)).encode("utf8")).hexdigest()[:6]
    name = base
    owner = project_owner(os.path.join(PROJECTS, base))
    coded_owner = project_owner(os.path.join(PROJECTS, f"{base}_{code}"))
    if coded_owner is not None and same_file(coded_owner, mask_file):
        name = f"{base}_{code}"                           # the user answered "no" before: its own folder
    elif owner is not None and not same_file(owner, mask_file) and os.path.exists(owner):
        same = ui.ask_yes_no(f"A project with the name {base} belongs to another file. Is this the same design?",
                             f"other file: {owner}. Yes = use its answers. No = new project", default="n")
        if same == "no":
            name = f"{base}_{code}"
            ui.note(f"Project folder for this file: {name}")
    folder = os.path.join(PROJECTS, name)
    os.makedirs(folder, exist_ok=True)
    with open(os.path.join(folder, "mask_file.txt"), "w", encoding="utf8") as f:
        f.write(os.path.abspath(mask_file))
    return folder


def change_one_part(stack):
    """Remove the saved answers of one part, so that the steps ask these questions again. Return the stack."""
    part = ui.ask_choice("Which part do you want to change?", "",
                         {"device": "Device", "stack": "Stack", "view": "View"}, default="stack",
                         details={"device": "Outline layer, device number, through holes.",
                                  "stack": "One layer, new layer on top, or full stack.",
                                  "view": "Part of device, cleave angle, layer spacing, coating distance, camera, "
                                          "dashed lines, labels."})
    if part == "device":
        remove = ["outline layer", "device number", "through holes"]
    elif part == "view":
        remove = [k for k in stack if step_of(k) == 4]     # all the render answers (step 4)
    else:
        count = 0
        while f"layer {count + 1} name" in stack:
            count += 1
        options = {str(n): f"Layer {n}: {stack[f'layer {n} name']}" for n in range(count, 0, -1)}   # top first
        options["add"] = "New layer on top"
        options["all"] = "Full stack again"
        layer = ui.ask_choice("Which layer?", "", options, default=str(count) if count else "all",
                              details={"add": "Adds a layer on top of the stack.",
                                       "all": "All layers again, bottom up."})
        if layer == "add":
            remove = [f"layer {count} has a layer on top"]
        elif layer == "all":
            remove = [k for k in stack if k.startswith("layer ")]
        else:                                             # all the answers of this layer, but not "has a layer on top"
            remove = [k for k in stack if k.startswith(f"layer {layer} ") and not k.endswith("has a layer on top")]
    answers.PREVIOUS.update({key: stack[key] for key in remove if key in stack})   # shown as default answers
    for key in remove:
        stack.pop(key, None)
    return stack


def answered_steps(stack):
    """The steps that have saved answers (step 1 = the start: always)."""
    return sorted({1} | {step_of(key) for key in stack if step_of(key)})


def load_or_start_stack(stack_file, mask_file):
    """Return the saved answers to use (a dictionary), and True if the user answered a question here.
    The old answers are never deleted.

    - Saved answers for this design exist: a short menu. Render again, change one part, or start new answers.
    - Else, a file "<mask file name>_stack.yaml" next to the mask file exists: the tool can start from it.
    """
    while os.path.exists(stack_file):
        options = {"render": "Render again with saved answers",
                   "change": "Change one part: device, stack or view",
                   "new": "Start new answers"}
        if ui.shows_forms():                              # the window: a click on a step changes its answers
            del options["change"]
            ui.steps_with_answers(answered_steps(answers.read_stack(stack_file)))
            ui.note("To change answers: click a step.")
        choice = ui.ask_choice(
            "This design has saved answers. What do you want to do?", "", options, default="render",
            details={"render": "Asks only for image quality.",
                     "change": "Asks only the questions of the selected part.",
                     "new": "Asks all questions again. Keeps a copy of old answers."})
        if choice == "render":
            return answers.read_stack(stack_file), True
        if choice == "change":
            try:
                return change_one_part(answers.read_stack(stack_file)), True
            except answers.GoBack:                        # back from "Which part?": this menu again
                answers.PREVIOUS.clear()
                continue
        copy = stack_file.replace("stack.yaml", f"stack_old_{time.strftime('%Y-%m-%d_%H-%M')}.yaml")
        os.replace(stack_file, copy)
        ui.show_path("Copy of old answers:", copy)
        return {}, True

    shared = os.path.splitext(mask_file)[0] + "_stack.yaml"
    if os.path.exists(shared):
        use = ui.ask_yes_no(f"{os.path.basename(shared)} has answers for this design. Use them?")
        if use == "yes":
            os.makedirs(os.path.dirname(stack_file), exist_ok=True)
            shutil.copy(shared, stack_file)
            return answers.read_stack(stack_file), True
        return {}, True
    return {}, False


def run(mask_file=None, go_to=None):
    """Do all the work. mask_file: a file given at the start; with None, the user selects it.
    go_to: a step (2 to 4) to open at once with the saved answers (a click on a step at the end of a run).
    Return the final image file."""
    global LAST_MASK_FILE
    answers.HISTORY.clear()                               # a new run starts clean (the window can run it again)
    answers.PREVIOUS.clear()
    answers.CURRENT_STEP, answers.SAVE = 0, None
    run_cache.clear()                                     # a new run never uses the results of an old run
    given = mask_file
    ask_file = not given
    while True:
        # The start: the mask file, then the saved answers. Esc goes back from the steps to here.
        if ask_file:
            try:
                mask_file = choose_mask_file()
            except answers.GoBack:
                ui.note("No earlier question.")
                continue
            except answers.GoToStep:                      # the start already: ask again
                continue
        LAST_MASK_FILE = mask_file
        ui.show_path("Mask file:", mask_file)
        project_folder = project_folder_for(mask_file)
        stack_file = os.path.join(project_folder, "stack.yaml")
        try:
            if go_to and os.path.exists(stack_file):      # a click on a step at the end: no start question
                stack, asked = answers.read_stack(stack_file), True
            else:
                stack, asked = load_or_start_stack(stack_file, mask_file)
                go_to = None
        except answers.GoBack:                            # back from the saved answers: the mask file question
            if given:
                ui.note("No earlier question.")
            ask_file = not given
            continue
        except answers.GoToStep as jump:                  # a click on a step at the start
            if jump.step < 2 or not os.path.exists(stack_file):
                ask_file = False                          # the start already: ask again
                continue
            stack, asked, go_to = answers.read_stack(stack_file), True, jump.step

        try:
            return run_steps(mask_file, stack, stack_file, project_folder, go_to)
        except BackToStart:
            go_to = None
            keep_old_answers(stack, stack_file)
            if asked or not given:
                ui.note("Back to start.")
            else:
                ui.note("No earlier question.")
            ask_file = not asked and not given            # no start question was asked: the mask file question
        except BaseException:
            # The user stopped (the window closed, Ctrl+C) or a problem stopped the run: the old answers that going
            # back or "change one part" removed, and that the user did not answer again, go back into stack.yaml.
            keep_old_answers(stack, stack_file)
            raise


def keep_old_answers(stack, stack_file):
    """The user went back to the start. Keep the old answers that "change one part" (or going back) removed and
    that the user did not answer again, so that no answer is lost."""
    for key, value in answers.PREVIOUS.items():
        stack.setdefault(key, value)
    answers.write_stack(stack_file, stack)
    answers.PREVIOUS.clear()
    answers.HISTORY.clear()


def run_steps(mask_file, stack, stack_file, project_folder, go_to=None):
    """Do the 5 steps, in order. Each step uses the results of the steps before it. Return the final image.
    go_to: a step whose questions come again at once (old answers = defaults); the steps before it keep their
    answers."""
    stack["dxf file"] = mask_file
    if go_to:
        for key in [k for k in stack if step_of(k) == go_to]:
            answers.PREVIOUS[key] = stack.pop(key)
    answers.SAVE = lambda values: answers.write_stack(stack_file, values)   # save after each answer
    results = {}
    steps = [
        lambda: step1_read_mask.run(mask_file, stack, project_folder),
        lambda: step2_pick_device.run(results[0], stack, project_folder),
        lambda: step3_layer_questions.run(results[1], stack, project_folder),
        lambda: step4_build_scene.run(results[1], results[2], stack, project_folder, PROJECTS),
        lambda: step5_labels.run(*results[3], project_folder),
    ]
    number = 0
    while number < len(steps):
        answers.CURRENT_STEP = number
        ui.steps_with_answers(answered_steps(stack))
        try:
            results[number] = steps[number]()
            answers.write_stack(stack_file, stack)         # save the answers after each step
            number += 1
        except answers.GoBack:
            if not answers.HISTORY:                        # no question before this one in the steps: the start
                raise BackToStart
            number, last_key = answers.HISTORY.pop()       # the last answer of this run: ask it again
            answers.PREVIOUS[last_key] = stack.pop(last_key)    # the old answer is the default answer
            answers.write_stack(stack_file, stack)
        except answers.GoToStep as jump:
            target = jump.step
            if target == 1:                                # step 1 (File) = the start
                raise BackToStart
            later = target > number + 1
            if later:
                # A later step: the steps before it keep their answers (the old answers come back), and they run
                # again with no question up to that step.
                for key in [k for k in answers.PREVIOUS if 0 < step_of(k) < target]:
                    stack.setdefault(key, answers.PREVIOUS.pop(key))
            # The answers of that step become the default answers, and its questions come again. The answers of
            # the later steps stay: these steps ask only the questions that have no answer.
            for key in [k for k in stack if step_of(k) == target]:
                answers.PREVIOUS[key] = stack.pop(key)
            answers.HISTORY[:] = [(step, key) for step, key in answers.HISTORY if step < target - 1]
            answers.write_stack(stack_file, stack)
            if not later:
                number = target - 1

    # The results, after the image of step 5: the Blender file (the 3D scene, to change in Blender), the answers.
    blend_file = os.path.splitext(results[3][1])[0] + ".blend"
    if os.path.exists(blend_file):
        ui.show_path("Blender file:", blend_file)
    ui.show_path("Answers saved in:", stack_file)
    return results[4]


def stop():
    """Stop the work that runs now (the front end calls this when the user closes the window)."""
    blender_runner.stop_blender()
