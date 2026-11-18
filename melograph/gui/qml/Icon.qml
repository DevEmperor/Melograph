import QtQuick
import QtQuick.Controls.impl

// Single-colour line icon from icons/<name>.svg, tinted
IconImage {
    property string iconName
    property int size: 18
    source: iconName ? Qt.resolvedUrl("icons/" + iconName + ".svg") : ""
    sourceSize: Qt.size(size, size)
    width: size
    height: size
    color: Theme.textDim
}
