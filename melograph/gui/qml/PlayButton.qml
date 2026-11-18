import QtQuick
import QtQuick.Controls.Basic

// Large round play button in the accent colour
AbstractButton {
    id: btn
    property bool playing: false

    implicitWidth: 46
    implicitHeight: 46
    focusPolicy: Qt.NoFocus
    hoverEnabled: true
    opacity: enabled ? 1 : 0.4

    background: Rectangle {
        radius: width / 2
        color: btn.pressed ? Qt.darker(Theme.accentStrong, 1.15) : (btn.hovered ? Qt.lighter(Theme.accentStrong, 1.12) : Theme.accentStrong)
        scale: btn.pressed ? 0.94 : 1
        Behavior on color { ColorAnimation { duration: Theme.animFast } }
        Behavior on scale { NumberAnimation { duration: Theme.animFast; easing.type: Easing.OutCubic } }
    }
    contentItem: Item {
        Icon {
            anchors.centerIn: parent
            anchors.horizontalCenterOffset: btn.playing ? 0 : 1
            iconName: btn.playing ? "pause-filled" : "play"
            size: 20
            color: "#ffffff"
        }
    }
}
