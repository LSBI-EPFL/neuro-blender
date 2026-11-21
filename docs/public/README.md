# Guides for developers

These guides are for a developer who changes the code of Neuro Blender: a person or an AI agent.
Read them in this order before you change the code:

1. [architecture.md](architecture.md): the parts of the code and how they work together.
2. [rules.md](rules.md): the rules for each change.
3. [testing.md](testing.md): the tests, and how to check a change.
4. [open_work.md](open_work.md): the known work that is not done.

The manual for the users of the tool is [../manual.md](../manual.md). It gives the questions, the keys, the
results, the answers file, the folder map and the limits.

## The tool

Neuro Blender makes an exploded-view image of a thin-film neural implant. The inputs are a mask file (DXF or GDS)
and the answers of the user to a series of questions. Blender 5.0 renders the image with no window (Cycles).

Neuro Blender is a lab tool. Clarity is more important than speed or scale. The user must always know what the tool
does and why it asks each question.

## Start

```
cd <path of the neuro-blender folder>
conda env create -f environment.yml
conda activate neuro-blender
python main.py
```

- `conda env create` is necessary one time only.
- `python main.py --terminal` asks the same questions in the terminal.
- `python tests/run_all.py` runs the tests (see [testing.md](testing.md)).
