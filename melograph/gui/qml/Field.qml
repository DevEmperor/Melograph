import QtQuick
import QtQuick.Controls.Basic

// One-line text input; the text is handed over when editing ends
TextField {
    id: field
    signal committed(string text)
    implicitHeight: 32
    color: Theme.text
    placeholderTextColor: Theme.textFaint
    selectionColor: Theme.accentSoft
    selectedTextColor: Theme.text
    font.pixelSize: 13
    leftPadding: 10
    rightPadding: 10
    selectByMouse: true
    background: Rectangle {
        radius: 8
        color: field.activeFocus ? Theme.surfaceHover : Theme.surface
        border.color: field.activeFocus ? Theme.accentStrong : Theme.border
        Behavior on border.color { ColorAnimation { duration: Theme.animFast } }
    }
    onEditingFinished: committed(text)
    Keys.onEscapePressed: focus = false
}
