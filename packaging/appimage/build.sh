#!/usr/bin/env bash
# Builds dist/Melograph-<version>-x86_64.AppImage.
#
# Inside: a portable CPython (python-build-standalone), PyTorch for the CPU,
# PySide6, everything else Melograph needs, PyAV so that any audio or video file
# opens without ffmpeg on the system, and the Beat This! model, so nothing is
# downloaded on the first start. It runs on x86_64 Linux with glibc 2.34 or newer
# (what the Qt of PySide6 asks for): Ubuntu 22.04, Debian 12, Fedora 35 and later.
#
# Downloads are kept in ~/.cache/melograph-build (about 400 MB, safe to delete);
# the AppDir is put together in build/appimage.
set -euo pipefail

here="$(cd "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")" && pwd)"
root="$(cd "$here/../.." && pwd)"
version="$(sed -n 's/^__version__ = "\(.*\)"$/\1/p' "$root/melograph/__init__.py")"
id="net.devemperor.Melograph"

python_release="20261110"
python_version="3.14.10"
python_sha256="c2ff2e97422f5d3896a16e0317fd212ba977bbf2688d93a6f7a03d817506bd30"
python_archive="cpython-$python_version+$python_release-x86_64-unknown-linux-gnu-install_only_stripped.tar.gz"
python_url="https://github.com/astral-sh/python-build-standalone/releases/download/$python_release/$python_archive"
tool_url="https://github.com/AppImage/appimagetool/releases/download/continuous/appimagetool-x86_64.AppImage"
beat_url="https://cloud.cp.jku.at/public.php/dav/files/7ik4RrBKTS273gp/final0.ckpt"
beat_sha256="8c328b45f59d8dd3dff219253ff6a8d6482be57d0133a29140e2febbf8eb8331"
update_info="gh-releases-zsync|DevEmperor|Melograph|latest|Melograph-*-x86_64.AppImage.zsync"

cache="${XDG_CACHE_HOME:-$HOME/.cache}/melograph-build"
work="$root/build/appimage"
appdir="$work/Melograph.AppDir"
dist="$root/dist"
target="$dist/Melograph-$version-x86_64.AppImage"

step() { printf '\n\033[1;31m●\033[0m %s\n' "$*"; }

fetch() {  # url, file name in the cache, sha256 (or empty)
    if [[ ! -s "$cache/$2" ]]; then
        curl -fL --retry 3 --progress-bar -o "$cache/$2.part" "$1"
        mv "$cache/$2.part" "$cache/$2"
    fi
    if [[ -n "$3" ]]; then
        echo "$3  $cache/$2" | sha256sum -c --quiet -
    fi
}

mkdir -p "$cache" "$work" "$dist"
echo "Melograph $version → $(basename "$target")"

step "Downloading the build tools"
fetch "$python_url" "$python_archive" "$python_sha256"
fetch "$tool_url" appimagetool-x86_64.AppImage ""
chmod +x "$cache/appimagetool-x86_64.AppImage"
# The beat model: the copy PyTorch already keeps on this computer, or a fresh download.
known="${TORCH_HOME:-${XDG_CACHE_HOME:-$HOME/.cache}/torch}/hub/checkpoints/beat_this-final0.ckpt"
if [[ ! -s "$cache/beat_this-final0.ckpt" && -s "$known" ]]; then
    command cp -f "$known" "$cache/beat_this-final0.ckpt"
fi
fetch "$beat_url" beat_this-final0.ckpt "$beat_sha256"

step "Portable Python $python_version"
rm -rf "$appdir"
mkdir -p "$appdir/usr"
tar -xzf "$cache/$python_archive" -C "$appdir/usr"  # → usr/python
py="$appdir/usr/python/bin/python3"
export PIP_DISABLE_PIP_VERSION_CHECK=1 PIP_CACHE_DIR="$cache/pip" PIP_NO_WARN_SCRIPT_LOCATION=1

step "PyTorch for the CPU"
# (The constraints pin the +cpu builds, so only the CPU index can provide them; the
# pinned versions of their dependencies come from PyPI.)
"$py" -m pip install --quiet -c "$here/constraints.txt" torch torchaudio \
    --index-url https://download.pytorch.org/whl/cpu --extra-index-url https://pypi.org/simple

step "Melograph and what it needs"
# From a clean copy of the sources, so that nothing left over in build/ slips in.
rm -rf "$work/source"
mkdir -p "$work/source"
command cp -rf "$root/melograph" "$root/pyproject.toml" "$root/README.md" "$root/LICENSE" "$work/source/"
find "$work/source" -name __pycache__ -prune -exec rm -rf {} +
"$py" -m pip install --quiet -c "$here/constraints.txt" "$work/source" av
# Transkun brings packages that only matter for training models; Melograph never loads them.
"$py" -m pip uninstall --quiet --yes \
    triton pandas seaborn tensorboard tensorboard-data-server grpcio protobuf \
    Werkzeug Markdown absl-py ncls torch-optimizer pytorch-ranger sox pydub 2>/dev/null || true

step "Leaving out what never runs"
python_lib="$appdir/usr/python/lib/python3.14"
site="$python_lib/site-packages"
# Python: its test suite, Tk and the IDLE editor, headers.
rm -rf "$python_lib/test" "$python_lib/idlelib" "$python_lib/tkinter" "$python_lib/turtledemo" \
    "$python_lib/ensurepip" "$python_lib"/lib-dynload/_tkinter* \
    "$appdir/usr/python/lib"/{tcl,tk,itcl,thread,tdbc}[0-9]* "$appdir/usr/python/lib"/lib{tcl,tk}[0-9]*.so* \
    "$appdir/usr/python/include" "$appdir/usr/python/share"
# PyTorch: headers and build files for writing extensions, and its own test programs.
rm -rf "$site/torch/include" "$site/torch/share" "$site/torch/lib"/*.a
find "$site/torch/bin" -mindepth 1 ! -name torch_shm_manager -exec rm -rf {} +
# PySide6: Qt's developer tools, headers, translations of Qt's own dialogs (Melograph has its
# own texts), and the Qt Quick styles other than Basic, which is the one Melograph draws on.
rm -rf "$site/PySide6"/{assistant,designer,linguist,lrelease,lupdate,qmlformat,qmllint,qmlls,svgtoqml} \
    "$site/PySide6"/{include,typesystems,glue,scripts,doc} \
    "$site/PySide6/Qt"/{include,metatypes,libexec,translations} \
    "$site/PySide6/Qt/qml/QtQuick/Controls"/{Fusion,Imagine,Material,Universal,FluentWinUI3,Native,designer} \
    "$site/PySide6/Qt/qml/QtQuick/NativeStyle" "$site/PySide6/Qt/qml/Qt/labs/StyleKit" \
    "$site/PySide6/Qt/lib"/libQt6QuickControls2{Fusion,Imagine,Material,Universal,FluentWinUI3,Native}*.so* \
    "$site/PySide6/Qt/lib"/libQt6{Designer,DesignerComponents,LabsStyleKit,LabsStyleKitImpl}.so* \
    "$site/PySide6"/{QtDesigner,QtLabsStyleKit}.*
rm -rf "$site/torch/test"  # C++ test programs
# music21's corpus of scores; Melograph only writes music. (Its test modules stay:
# music21 imports them when it starts.)
find "$site/music21/corpus" -mindepth 1 -maxdepth 1 -type d ! -name __pycache__ -exec rm -rf {} +
pip_left="$("$py" -c 'import pip, os; print(os.path.dirname(pip.__file__))')"
"$py" -m pip uninstall --quiet --yes pip
rm -rf "$pip_left"
# Byte code once now: an AppImage is read-only, so Python could not keep it later.
find "$appdir/usr/python" -name __pycache__ -prune -exec rm -rf {} +
"$py" -I -W ignore -m compileall -q -j0 -o 1 "$appdir/usr/python/lib" >/dev/null || true

step "Model, menu entry, icon"
install -Dm755 "$here/AppRun" "$appdir/AppRun"
install -Dm644 "$cache/beat_this-final0.ckpt" "$appdir/usr/share/melograph/beat_this-final0.ckpt"
install -Dm644 "$root/melograph/gui/$id.desktop" "$appdir/usr/share/applications/$id.desktop"
install -Dm644 "$root/data/$id.metainfo.xml" "$appdir/usr/share/metainfo/$id.appdata.xml"
install -Dm644 "$root/melograph/gui/icons/$id.svg" "$appdir/usr/share/icons/hicolor/scalable/apps/$id.svg"
install -Dm644 "$root/LICENSE" "$appdir/usr/share/licenses/melograph/LICENSE"
install -Dm644 "$root/THIRD-PARTY.md" "$appdir/usr/share/licenses/melograph/THIRD-PARTY.md"
ln -sf "usr/share/applications/$id.desktop" "$appdir/$id.desktop"
ln -sf "usr/share/icons/hicolor/scalable/apps/$id.svg" "$appdir/$id.svg"
if command -v rsvg-convert >/dev/null; then
    rsvg-convert -w 256 -h 256 "$root/melograph/gui/icons/$id.svg" -o "$appdir/.DirIcon"
else
    ln -sf "$id.svg" "$appdir/.DirIcon"
fi

step "Which glibc it needs"
needed="$(find "$appdir" -type f \( -name '*.so*' -o -perm -u+x \) -exec objdump -T {} + 2>/dev/null \
    | grep -o 'GLIBC_[0-9.]*' | sort -uV | tail -1)" || true  # objdump also sees scripts and fails on them
echo "highest symbol version: ${needed:-unknown}"

step "Packing the AppImage"
rm -f "$target" "$target.zsync"
# zstd with 1 MB blocks at level 19: about 8 % smaller than the default, and still quick to unpack.
(cd "$dist" && ARCH=x86_64 APPIMAGE_EXTRACT_AND_RUN=1 "$cache/appimagetool-x86_64.AppImage" \
    --no-appstream -u "$update_info" \
    --mksquashfs-opt -b --mksquashfs-opt 1M --mksquashfs-opt -Xcompression-level --mksquashfs-opt 19 \
    "$appdir" "$target")
echo
echo "AppDir: $(du -sh "$appdir" | cut -f1) · AppImage: $(du -h "$target" | cut -f1)"
echo "$target"
