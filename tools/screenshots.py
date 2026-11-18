"""Pictures of the window for the README and for checking the interface – without showing anything.

Runs Melograph offscreen with its own settings, history and cache folders and
with silent sound, opens a piece, walks through the views and saves PNGs.

    .venv/bin/python tools/screenshots.py recording.mp3 [folder] [--light] [--de]
        [--app dist/Melograph-…-x86_64.AppImage]   walk through a built AppImage instead
        [--fresh]                                  transcribe again instead of reusing the cache
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

STEPS = r'''
import os
from pathlib import Path
out = Path(os.environ["SHOTS"])
piece = os.environ["PIECE"]

def grab(name):
    window.grabWindow().save(str(out / f"{name}.png"))
    print("shot", name, flush=True)

def later(ms, fn):
    QTimer.singleShot(ms, fn)

def wait(condition, then, tries=600):
    if condition() or tries <= 0:
        then()
    else:
        QTimer.singleShot(200, lambda: wait(condition, then, tries - 1))

def start():
    grab("1-welcome")
    controller.openFile(piece)
    later(1200, lambda: grab("2-working"))
    wait(lambda: controller.page == "score" and controller.result.get("pages"), score)

def score():
    later(2500, lambda: (grab("3-score"), playing()))

def playing():
    player.seek(17.0)
    player.play()
    wait(lambda: player.scoreReady, lambda: later(1800, lambda: (grab("4-playing"), roll())))

def roll():
    controller.setPreference("view", "roll")
    later(900, lambda: (grab("5-roll"), back()))

def back():
    player.pause()
    controller.setPreference("view", "score")
    controller.setOption("chords", True)
    wait(lambda: not controller.busy, lambda: later(1500, lambda: (grab("6-chords"), finish())))

def finish():
    controller.setOption("chords", False)
    wait(lambda: not controller.busy, lambda: later(800, menus))

def popup(name):
    from PySide6.QtCore import QObject
    return window.findChild(QObject, name)

def menus():
    popup("exportMenu").open()
    later(500, lambda: (grab("7-export"), popup("exportMenu").close(), later(300, prefs)))

def prefs():
    popup("preferences").open()
    if controller.canAddToMenu:
        controller.setInMenu(True)
        print("menu entry:", controller.inMenu, flush=True)
    later(600, lambda: (grab("8-preferences"), popup("preferences").close(), later(400, record)))

def record():
    popup("recordDialog").open()
    later(500, lambda: (grab("9-record"), recorder.start(), later(1600, recording)))

def recording():
    grab("10-recording")
    recorder.stop(os.environ["RECORDINGS"])
    popup("recordDialog").close()
    later(600, lambda: grab("11-silence-working"))
    wait(lambda: controller.page == "welcome", lambda: later(400, lambda: (grab("12-after-silence"), fresh())))

def fresh():
    controller.openFile(piece)
    wait(lambda: controller.page == "score", lambda: later(1500, again))

def again():
    controller.listenAgain()
    wait(lambda: controller.progress > 0.2, lambda: (grab("13-listening"),
         wait(lambda: controller.page == "score", lambda: later(1200, lambda: (grab("14-home"), app.quit())))))

wait(lambda: True, start)
'''


def main() -> int:
    piece = Path(sys.argv[1]).resolve()
    out = Path(sys.argv[2] if len(sys.argv) > 2 and not sys.argv[2].startswith("--") else "screenshots").resolve()
    theme = "light" if "--light" in sys.argv else "dark"
    language = "de" if "--de" in sys.argv else "en"
    app = next((sys.argv[i + 1] for i, a in enumerate(sys.argv[:-1]) if a == "--app"), None)
    out.mkdir(parents=True, exist_ok=True)
    root = Path(__file__).resolve().parents[1]
    with tempfile.TemporaryDirectory(prefix="melograph-shots-") as temp:
        temp = Path(temp)
        for name in ("config", "data", "cache", "runtime", "recordings", "torch"):
            (temp / name).mkdir()
        os.chmod(temp / "runtime", 0o700)
        # Reuse what was already heard, so the pictures do not wait for a transcription.
        real_cache = Path(os.environ.get("XDG_CACHE_HOME") or Path.home() / ".cache") / "melograph"
        if real_cache.exists() and "--fresh" not in sys.argv:
            shutil.copytree(real_cache, temp / "cache" / "melograph", dirs_exist_ok=True)
        # An AppImage brings its own beat model: an empty PyTorch folder proves it needs no download.
        torch_home = str(temp / "torch") if app else os.environ.get("TORCH_HOME") or str(Path.home() / ".cache" / "torch")
        steps = temp / "steps.py"
        steps.write_text(STEPS)
        env = dict(
            os.environ,
            QT_QPA_PLATFORM="offscreen", QT_QPA_PLATFORMTHEME="", MELOGRAPH_MUTE="1",
            MELOGRAPH_TEST_STEPS=str(steps), MELOGRAPH_THEME=theme, MELOGRAPH_LANG=language,
            RECORDINGS=str(temp / "recordings"),
            XDG_CONFIG_HOME=str(temp / "config"), XDG_DATA_HOME=str(temp / "data"),
            XDG_CACHE_HOME=str(temp / "cache"), XDG_RUNTIME_DIR=str(temp / "runtime"),
            SHOTS=str(out), PIECE=str(piece), TORCH_HOME=torch_home,
        )
        env.pop("WAYLAND_DISPLAY", None)
        env.pop("DISPLAY", None)
        command = [str(Path(app).resolve()), "--gui"] if app else [sys.executable, "-m", "melograph.gui"]
        result = subprocess.call(command, cwd=root, env=env, timeout=900)
        if app:
            downloaded = list((temp / "torch").rglob("*.ckpt"))
            print("beat model downloaded:", ", ".join(map(str, downloaded)) if downloaded else "no")
        return result


if __name__ == "__main__":
    raise SystemExit(main())
