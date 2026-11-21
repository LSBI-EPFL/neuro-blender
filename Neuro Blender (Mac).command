#!/bin/bash
# Neuro Blender for Mac: double-click this file to open the window of the tool.
# It needs Miniconda or Anaconda and the conda environment "neuro-blender". README.md, section "Install", tells how
# to make the environment one time. The first time, macOS can block the file: right-click it, then select "Open".

cd "$(dirname "$0")" || exit 1

stop() {
    echo "$1"
    read -r -p "Push Enter to close this window."
    exit 1
}

# Find conda: first in the usual install folders, then in the PATH.
CONDA=""
for base in "$HOME/miniconda3" "$HOME/anaconda3" "$HOME/miniforge3" "$HOME/opt/miniconda3" "$HOME/opt/anaconda3" \
            "/opt/miniconda3" "/opt/anaconda3" "/opt/homebrew/Caskroom/miniconda/base" \
            "/usr/local/Caskroom/miniconda/base"; do
    if [ -x "$base/bin/conda" ]; then
        CONDA="$base/bin/conda"
        break
    fi
done
[ -z "$CONDA" ] && CONDA="$(command -v conda)"
[ -z "$CONDA" ] && stop "Conda was not found. Install Miniconda or Anaconda: see README.md, section \"Install\"."

# Activate the environment, then open the window.
eval "$("$CONDA" shell.bash hook)"
conda activate neuro-blender 2>/dev/null || stop "The conda environment \"neuro-blender\" does not exist. Make it one time: see README.md, section \"Install\"."
python main.py
