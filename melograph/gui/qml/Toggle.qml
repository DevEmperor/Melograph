import QtQuick
import QtQuick.Controls.Basic

// Slim on/off switch in the accent colour
AbstractButton {
    id: toggle
    checkable: true
    implicitWidth: 38
    implicitHeight: 22
    focusPolicy: Qt.NoFocus
    hoverEnabled: true

    background: Rectangle {
        radius: height / 2
        color: toggle.checked ? Theme.accentStrong : (toggle.hovered ? Theme.surfacePressed : Theme.surfaceHover)
        Behavior on color { ColorAnimation { duration: Theme.animFast } }
        Rectangle {
            width: parent.height - 6
            height: width
            radius: width / 2
            y: 3
            x: toggle.checked ? parent.width - width - 3 : 3
            color: toggle.checked ? "#ffffff" : Theme.textDim
            Behavior on x { NumberAnimation { duration: Theme.anim; easing.type: Easing.OutCubic } }
        }
    }
}
