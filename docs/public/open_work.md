# Open work

This list gives the known work that is not done. Do each item as a series of small changes (see [rules.md](rules.md)).

## Defect

**The step 3 form does not save before Next.** The window saves the answers of the step 3 form only when the user
pushes Next. If the user closes the window while the form is open, the changes in the form are lost.

## Structure

1. **The question thread of the window.** The back end runs in a thread and waits for each answer. Now that steps 3
   and 4 use forms, the thread and the replay of steps after a GoToStep can become simpler. Fewer results in
   `backend/run_cache.py` are then necessary.
2. **A typed data model.** The answers are one flat dictionary of texts, and the logic depends on text conventions
   (example: `"layer 2 materials"`). Typed classes for a layer, the stack and the render values make the code safer.
   Change one part at a time, and keep the format of `stack.yaml`.
3. **The size of `frontends/window.py`.** The file has about 1 070 lines. Split it into smaller files, one job each.
4. **Screen texts in many files.** Many back-end files hold screen texts. One place for them makes the language
   easier to check.

## Geometry and tests

1. **One test design.** The tests use one design (`tests/design/`). The hard cases (a narrow neck, a round device)
   are unit tests only. Add test designs for these cases. Draw each one only for the tests.
2. **Fixed crop values in step 4.** The crop of the "electrodes" view in `build_scene()` uses fixed values
   (`hinge = site_start - 0.25 × size`, `crop_start = hinge - 0.5 × size`). The crop line can cut through pad
   openings, and the cut edge then shows notches. The test design keeps its pads below the crop line. Calculate the
   values from the shapes of the design.
3. **No automatic test runs.** The repository has no CI file. Only the owner of the repository decides if one is
   necessary.
