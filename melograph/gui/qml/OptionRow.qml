import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts

// A setting: its name on the left, the control on the right
RowLayout {
    id: row
    property string label
    property string tip
    default property alias control: holder.data
    spacing: 10
    Layout.fillWidth: true

    Text {
        Layout.fillWidth: true
        text: row.label
        color: Theme.textDim
        font.pixelSize: 12
        elide: Text.ElideRight
        HoverHandler { id: hover }
        ToolTip.visible: hover.hovered && row.tip.length > 0
        ToolTip.delay: 500
        ToolTip.text: row.tip
    }
    Item {
        id: holder
        implicitWidth: childrenRect.width
        implicitHeight: Math.max(26, childrenRect.height)
    }
}
