pragma Singleton
import QtQuick

// Colours, sizes and motion as in QuickBible: near black, red accent; light mode follows the desktop
QtObject {
    readonly property bool dark: appearance.dark
    function pick(d, l) {
        return dark ? d : l
    }

    readonly property color bg: pick("#0e0c0f", "#faf8f8")
    readonly property color panel: pick("#141115", "#f3efef")
    readonly property color raised: pick("#1c181d", "#ffffff")
    readonly property color surface: pick(Qt.rgba(1, 1, 1, 0.055), Qt.rgba(0, 0, 0, 0.04))
    readonly property color surfaceHover: pick(Qt.rgba(1, 1, 1, 0.095), Qt.rgba(0, 0, 0, 0.065))
    readonly property color surfacePressed: pick(Qt.rgba(1, 1, 1, 0.13), Qt.rgba(0, 0, 0, 0.10))
    readonly property color border: pick(Qt.rgba(1, 1, 1, 0.09), Qt.rgba(0, 0, 0, 0.09))

    readonly property color text: pick("#f1eff1", "#17131a")
    readonly property color textDim: pick("#b3adb4", "#4f4851")
    readonly property color textFaint: pick("#8d868f", "#6f6670")

    readonly property color accent: pick("#ff767a", "#c62c32")
    readonly property color accentStrong: pick("#e5484d", "#d42e33")
    readonly property color accentSoft: Qt.rgba(0.898, 0.282, 0.302, pick(0.22, 0.12))
    readonly property color leftHand: pick("#6aa8e0", "#2f6fb0")
    readonly property color danger: pick("#e5484d", "#d42e33")
    readonly property color paper: "#ffffff"
    readonly property color desk: pick("#0a090b", "#e7e2e3")

    readonly property int radius: 16
    readonly property int radiusSmall: 9
    readonly property int animFast: 130
    readonly property int anim: 220
    readonly property int animSlow: 360
}
