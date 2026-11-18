#!/usr/bin/env bash
# Starts Melograph: without arguments the window, with files the command line.
# On the very first start it sets up its own Python environment next to this
# script (a few minutes, about 1.8 GB – PyTorch is installed without CUDA).
set -euo pipefail

here="$(cd "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")" && pwd)"
venv="$here/.venv"

if [[ ! -x "$venv/bin/python" ]] || ! "$venv/bin/python" -c "import melograph, transkun, beat_this, music21, verovio, PySide6, miniaudio" 2>/dev/null; then
    echo "Melograph: first start – installing what it needs (a few minutes) …"
    python3 -m venv "$venv"
    "$venv/bin/python" -m pip install --quiet --upgrade pip
    # PyTorch for the CPU: a fraction of the size of the CUDA build, and fast enough.
    "$venv/bin/python" -m pip install --quiet torch torchaudio --index-url https://download.pytorch.org/whl/cpu
    "$venv/bin/python" -m pip install --quiet -e "$here"
    # Transkun brings packages that only matter for training models; Melograph never loads them.
    "$venv/bin/python" -m pip uninstall --quiet --yes \
        triton pandas seaborn tensorboard tensorboard-data-server grpcio protobuf \
        Werkzeug Markdown absl-py ncls torch-optimizer pytorch-ranger sox pydub 2>/dev/null || true
    "$venv/bin/python" -m pip cache purge >/dev/null 2>&1 || true
fi

exec "$venv/bin/python" -m melograph "$@"
