import QtQuick
import QtQuick.Controls.Basic

// Flat, rounded button with an icon, an optional label, and a tooltip
AbstractButton {
    id: btn
    property string iconName
    property string label
    property string tip
    property int iconSize: 18
    property bool active: false
    property color iconColor: active ? Theme.accent : (hovered ? Theme.text : Theme.textDim)

    implicitWidth: label ? row.implicitWidth + 20 : 34
    implicitHeight: 34
    focusPolicy: Qt.NoFocus
    hoverEnabled: true
    opacity: enabled ? 1 : 0.4

    background: Rectangle {
        radius: Theme.radiusSmall
        color: btn.pressed ? Theme.surfacePressed
                           : (btn.active ? Theme.accentSoft : (btn.hovered ? Theme.surfaceHover : "transparent"))
        Behavior on color { ColorAnimation { duration: Theme.animFast } }
    }
    contentItem: Item {
        Row {
            id: row
            anchors.centerIn: parent
            spacing: 7
            Icon {
                anchors.verticalCenter: parent.verticalCenter
                iconName: btn.iconName
                size: btn.iconSize
                color: btn.iconColor
                Behavior on color { ColorAnimation { duration: Theme.animFast } }
            }
            Text {
                visible: btn.label.length > 0
                anchors.verticalCenter: parent.verticalCenter
                text: btn.label
                color: btn.active ? Theme.accent : (btn.hovered ? Theme.text : Theme.textDim)
                font.pixelSize: 13
                Behavior on color { ColorAnimation { duration: Theme.animFast } }
            }
        }
    }

    ToolTip.visible: hovered && tip.length > 0
    ToolTip.delay: 600
    ToolTip.text: tip
}
