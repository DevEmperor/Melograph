import QtQuick
import QtQuick.Layouts

// A group of settings with a small heading
ColumnLayout {
    id: section
    property string title
    default property alias content: body.data
    spacing: 8
    Layout.fillWidth: true

    Text {
        text: section.title.toUpperCase()
        color: Theme.textFaint
        font.pixelSize: 11
        font.letterSpacing: 1.1
        font.weight: Font.DemiBold
        Layout.topMargin: 6
    }
    ColumnLayout {
        id: body
        spacing: 8
        Layout.fillWidth: true
    }
}
