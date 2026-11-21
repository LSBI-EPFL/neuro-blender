# Rules for a change

## Ask before you make

- Do only the work that the owner of the repository asks for.
- Do not make a repository, a branch, a CI file, a new folder or a new tool unless the owner asks for it.
- When the owner asks a question, answer the question. Do not start work.
- Ask before you delete or overwrite a file that you did not make.

## Language

All text in the repository uses ASD-STE100 Simplified Technical English. This rule applies to the documents, the
docstrings, the code comments, the screen texts, the messages and the commit messages.

- Write short sentences in the active voice.
- Use one term for one thing.
- Do not use idioms.

## Small, proven changes

- Give each change one topic. Keep each commit small, so that a person can review it.
- Do not rewrite large parts of the code in one change.
- Before you repair a defect, find its real cause and prove it with a test or with data.
- Give each repair a test that fails before the repair and passes after it.
- Run `python tests/run_all.py` before each commit.
- Also run `python tests/run_all.py --all` when you change the window, the geometry or the render.

## Where the code goes

- Put all logic in the back end. A front end only shows the messages and returns the answers.
- Write a new question as a `Question` (`backend/questions.py`). Write its text, default answer and check one time.
- Put a change of the Blender scene format into `backend/blender_protocol.py`, and increase `SCENE_FORMAT`.
- Put a change of the answers file format into `backend/answers.py`, with a conversion of the old format.

## The product

- Keep the tool clear. Do not add batch modes, speed options or scale features.
- Give each question a help text and a good default answer.
- Never drop data in silence. If the tool cannot use a shape or an answer, it shows a warning.
- The user interface does not offer the example designs. They are for the tests only.

## The data of the user

- Never put files from `my_designs/` or `projects/` into the repository.
- Never put private paths, names or designs into the code, the tests or the documents.
- Do not delete a `stack.yaml` file or a project folder without the approval of the user.
- After a test run, make sure that `tests/design/linear_probe_stack.yaml` did not change.
- A new test design must be drawn only for the tests. Never copy a real device of the user.

## The screen and Blender

- Do not take screen captures to check the window. A capture can show private content of the computer.
  Use `tests/window_drawing.py`: it draws a window from its widget data.
- An AI agent does not run a Blender job of more than about 2 minutes itself. It gives the command to the user.
