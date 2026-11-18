import QtQuick
import QtQuick.Controls.Basic

// Text button, optionally with an icon; "emphasized" fills it with the accent colour
AbstractButton {
    id: button
    property bool emphasized: false
    property string iconName: ""
    property bool large: false
    implicitHeight: large ? 40 : 30
    implicitWidth: row.implicitWidth + (large ? 34 : 24)
    focusPolicy: Qt.NoFocus
    hoverEnabled: true
    opacity: enabled ? 1 : 0.45

    background: Rectangle {
        radius: button.large ? 11 : 8
        color: button.emphasized ? (button.pressed ? Qt.darker(Theme.accentStrong, 1.12)
                                                   : button.hovered ? Qt.lighter(Theme.accentStrong, 1.1) : Theme.accentStrong)
                                 : (button.pressed ? Theme.surfacePressed : (button.hovered ? Theme.surfaceHover : Theme.surface))
        border.color: button.emphasized ? "transparent" : Theme.border
        Behavior on color { ColorAnimation { duration: Theme.animFast } }
    }
    contentItem: Item {
        Row {
            id: row
            anchors.centerIn: parent
            spacing: 8
            Icon {
                visible: button.iconName.length > 0
                anchors.verticalCenter: parent.verticalCenter
                iconName: button.iconName
                size: button.large ? 18 : 15
                color: button.emphasized ? "#ffffff" : Theme.text
            }
            Text {
                anchors.verticalCenter: parent.verticalCenter
                text: button.text
                color: button.emphasized ? "#ffffff" : Theme.text
                font.pixelSize: button.large ? 14 : 12
                font.weight: button.large ? Font.DemiBold : Font.Normal
            }
        }
    }
}
