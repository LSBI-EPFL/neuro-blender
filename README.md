# Neuro Blender

Neuro Blender makes an exploded-view image of a thin-film implant from its mask file (DXF or GDS) and your
answers to a series of questions. Blender (a free 3D program) renders the image. The tool has a window (GUI) and
the same questions in the terminal (TUI).

## Install (one time)

You need Anaconda or Miniconda and Blender. Open the terminal ("Anaconda Prompt" on Windows) and type these
commands. Replace `<folder>` with the full path of the neuro-blender folder.

```
cd "<folder>"
conda env create -f environment.yml
```

## Start the tool

### Option 1: double-click

Double-click the start file in the neuro-blender folder:
- Windows: `Neuro Blender (Windows).bat`
- Mac: `Neuro Blender (Mac).command`

The start file activates the conda environment and opens the window.

On a Mac, the first start can be blocked by macOS. Right-click the file, then select **Open**.

### Option 2: the terminal

```
cd "<folder>"
conda activate neuro-blender
python main.py
```

`python main.py --terminal` asks the same questions in the terminal.

## Documents

All the documents are in the folder [`docs/`](docs/):
- [`docs/manual.md`](docs/manual.md): the full manual. The questions, the keys, the results, the answers file,
  the folder map and the limits.
- [`docs/public/`](docs/public/): the guides for developers (people and AI agents) who change the code.
