"""Starts the window."""

from __future__ import annotations

import os
import signal
import sys
from pathlib import Path

APP_ID = "net.devemperor.Melograph"
HERE = Path(__file__).parent


def _platform_theme() -> list[str]:
    """The desktop's own file dialogs: KDE's on Plasma, GTK's on GNOME.

    PySide6 brings a Qt of its own, which cannot load the KDE integration installed
    for the system's Qt; without help it falls back to file dialogs drawn in QML.
    The XDG desktop portal is how Flatpaks and AppImages reach the real ones. A theme
    the user chose that this Qt has (gtk3, say) is kept. Passed as an argument rather
    than through the environment, so that MuseScore, started from here, keeps its own.
    """
    from PySide6.QtCore import QLibraryInfo

    folder = Path(QLibraryInfo.path(QLibraryInfo.LibraryPath.PluginsPath)) / "platformthemes"
    available = {p.name[4:].split(".")[0] for p in folder.glob("libq*.so")}  # libqgtk3.so → gtk3
    chosen = os.environ.get("QT_QPA_PLATFORMTHEME", "")
    if chosen in available or "xdgdesktopportal" not in available:
        return []
    return ["-platformtheme", "xdgdesktopportal"]


def run(files: list[str] | None = None) -> int:
    from PySide6.QtCore import Property, QObject, Qt, QTimer, Signal
    from PySide6.QtGui import QGuiApplication, QIcon
    from PySide6.QtQml import QQmlApplicationEngine, qmlRegisterType
    from PySide6.QtQuickControls2 import QQuickStyle

    from ..render import register_fonts
    from .controller import Controller
    from .items import PianoRoll, Waveform

    QQuickStyle.setStyle("Basic")
    app = QGuiApplication(sys.argv[:1] + _platform_theme())
    app.setApplicationName("Melograph")
    app.setApplicationDisplayName("Melograph")
    app.setOrganizationDomain("devemperor.net")
    app.setDesktopFileName(APP_ID)
    app.setWindowIcon(QIcon(str(HERE / "icons" / f"{APP_ID}.svg")))
    register_fonts()

    class Appearance(QObject):
        """Light or dark, following the desktop."""

        changed = Signal()

        @Property(bool, notify=changed)
        def dark(self) -> bool:
            forced = os.environ.get("MELOGRAPH_THEME")
            if forced in ("dark", "light"):
                return forced == "dark"
            return app.styleHints().colorScheme() != Qt.ColorScheme.Light

    appearance = Appearance()
    app.styleHints().colorSchemeChanged.connect(lambda *_: appearance.changed.emit())

    qmlRegisterType(Waveform, "Melograph", 1, 0, "Waveform")
    qmlRegisterType(PianoRoll, "Melograph", 1, 0, "PianoRoll")

    controller = Controller()
    engine = QQmlApplicationEngine()
    context = engine.rootContext()
    context.setContextProperty("controller", controller)
    context.setContextProperty("player", controller.player)
    context.setContextProperty("recorder", controller.recorder)
    context.setContextProperty("appearance", appearance)
    engine.load(HERE / "qml" / "Main.qml")
    if not engine.rootObjects():
        controller.shutdown()
        return 1
    window = engine.rootObjects()[0]

    def fills_screen():
        screen = window.screen()
        if screen is not None:
            free = screen.availableGeometry()
            window.setProperty("fillsScreen", window.width() >= free.width() - 2 and window.height() >= free.height() - 2)

    for changed in (window.widthChanged, window.heightChanged, window.screenChanged):
        changed.connect(fills_screen)
    fills_screen()

    for file in files or []:
        controller.openFile(str(Path(file).resolve()))
    from .menu import follow_move

    follow_move()

    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, lambda *_: app.quit())
    wake = QTimer()  # lets Python handle signals while Qt's event loop runs
    wake.timeout.connect(lambda: None)
    wake.start(250)

    # Only for automatic UI tests: run Python steps and save pictures of the window.
    if os.environ.get("MELOGRAPH_TEST_STEPS"):
        scope = {"controller": controller, "window": window, "QTimer": QTimer, "app": app,
                 "player": controller.player, "recorder": controller.recorder}
        QTimer.singleShot(800, lambda: exec(Path(os.environ["MELOGRAPH_TEST_STEPS"]).read_text(), scope))
    app.aboutToQuit.connect(controller.shutdown)
    result = app.exec()
    del engine
    return result


def main() -> int:
    files = [a for a in sys.argv[1:] if not a.startswith("-")]
    return run(files)


if __name__ == "__main__":
    raise SystemExit(main())
