import QtQuick
import QtQuick.Controls.Basic

// Segmented choice as in QuickBible: [{text, value}] or [{icon, text (tooltip), value}], the chosen value in "value"
Rectangle {
    id: segments
    property var options: []
    property var value
    property int itemPadding: 18
    property bool stretch: false  // spread the segments over the full width
    signal chosen(var value)

    implicitWidth: row.implicitWidth + 6
    implicitHeight: 30
    radius: 9
    color: Theme.surface
    border.color: Theme.border

    Row {
        id: row
        anchors.centerIn: parent
        spacing: 2
        Repeater {
            model: segments.options
            delegate: AbstractButton {
                id: button
                readonly property bool on: modelData.value === segments.value
                readonly property bool iconOnly: !!modelData.icon
                readonly property color tint: button.on ? Theme.accent : (button.hovered ? Theme.text : Theme.textDim)
                implicitHeight: 24
                implicitWidth: segments.stretch ? (segments.width - 6 - 2 * (segments.options.length - 1)) / segments.options.length
                                                : (iconOnly ? 16 : label.implicitWidth) + segments.itemPadding
                focusPolicy: Qt.NoFocus
                hoverEnabled: true
                enabled: modelData.enabled === undefined || modelData.enabled
                opacity: enabled ? 1 : 0.4
                background: Rectangle {
                    radius: 7
                    color: button.on ? Theme.accentSoft : (button.hovered ? Theme.surfaceHover : "transparent")
                    Behavior on color { ColorAnimation { duration: Theme.animFast } }
                }
                contentItem: Item {
                    Text {
                        id: label
                        anchors.centerIn: parent
                        visible: !button.iconOnly
                        text: modelData.text
                        color: button.tint
                        font.pixelSize: 12
                    }
                    Icon {
                        anchors.centerIn: parent
                        visible: button.iconOnly
                        iconName: modelData.icon || ""
                        size: 16
                        color: button.tint
                    }
                }
                ToolTip.visible: (iconOnly || !!modelData.tip) && hovered
                ToolTip.delay: 500
                ToolTip.text: modelData.tip || modelData.text
                onClicked: segments.chosen(modelData.value)
            }
        }
    }
}
