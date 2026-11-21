# Neuro Blender

Neuro Blender makes an exploded-view image of a thin-film implant from its mask file (DXF or GDS) and your
answers to a series of questions. Blender (a free 3D program) renders the image. The tool has a window (GUI) and
the same questions in the terminal (TUI).

## What you need

- A computer with Windows or macOS.
- **Blender** 5.0 or newer (free): it renders the 3D image.
- **Python**, from Anaconda or Miniconda (free): the tool is written in Python.
- **The mask file of your implant**: a DXF file or a GDS file.
- **Knowledge of your implant**: the tool asks about its layers, materials, thicknesses and colours.

## How it works

1. **File:** you select the mask file. The tool shows its mask layers.
2. **Device:** you select the mask layer of the device outline and the device to show.
3. **Stack:** you describe the layers of the device, from the bottom to the top: materials, thicknesses, colours
   and openings.
4. **Render:** you select a view from test images. Blender renders the 3D image.
5. **Labels:** the tool puts the name and the real thickness of each layer on the image.

The tool saves each answer. The next time that you use the same mask file, you can render again with the same
answers, or change some of them.

## Install (one time)

### 1. Install the programs

1. Install **Blender** from https://www.blender.org/download. Use the default settings.
2. Install **Miniconda** (or Anaconda) from https://www.anaconda.com/download. Use the default settings. It
   installs Python.
3. Optional: install **Git** from https://git-scm.com/downloads. Git downloads the tool with one command and
   gets the updates.

### 2. Download Neuro Blender

**Option A: with Git**
1. At the top of this page, click the green **Code** button and copy the HTTPS address.
2. Open the terminal: on Windows, open **Anaconda Prompt** from the Start menu; on a Mac, open **Terminal**.
3. Type these commands. Paste the address that you copied in place of `<address>`.
   ```
   cd path_of_your_choice
   git clone <address>
   ```
   The tool is now in the folder you created `path_of_your_choice/neuro-blender`.

**Option B: without Git**
1. At the top of this page, click the green **Code** button, then **Download ZIP**.
2. Extract the ZIP file into your `path_of_your_choice` folder.
3. Rename the extracted folder from `neuro-blender-main` to `neuro-blender`.

### 3. Make the Python environment

The environment is a separate Python installation with the packages that the tool needs.

1. Open the terminal: **Anaconda Prompt** on Windows, **Terminal** on a Mac.
2. Type these commands:
   ```
   cd path_of_your_choice/neuro-blender
   conda env create -f environment.yml
   ```
   This takes some minutes.

## Start the tool

### Option 1: double-click

Double-click the start file in the `neuro-blender` folder:
- Windows: `Neuro Blender (Windows).bat`
- Mac: `Neuro Blender (Mac).command`

The start file activates the Python environment and opens the window.

On a Mac, the first start can be blocked by macOS. Right-click the file, then select **Open**.

### Option 2: the terminal

```
cd path_of_your_choice/neuro-blender
conda activate neuro-blender
python main.py
```

`python main.py --terminal` asks the same questions in the terminal.

### The first start

- If the tool does not find Blender, it asks you to select the Blender program. It asks one time only.
- Put your mask files into the folder `my_designs`, and the tool shows them in a list. You can also select a mask
  file from any other folder.

## Your results

The tool puts the results into the folder `projects/<name of your mask file>/`:
- `6_exploded_view.png`: the exploded-view image, with the labels.
- `5_render.blend`: the 3D scene. Open it in Blender to change it by hand.
- `stack.yaml`: your answers.

## Documents

All the documents are in the folder [`docs/`](docs/):
- [`docs/manual.md`](docs/manual.md): the full manual. The questions, the keys, the results, the answers file,
  the folder map and the limits.
- [`docs/public/`](docs/public/): the guides for developers (people and AI agents) who change the code.
