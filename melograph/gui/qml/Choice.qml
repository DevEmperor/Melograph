import QtQuick
import QtQuick.Controls.Basic

// Drop-down choice in the style of the app: choices [{text, value}], the chosen value in "current"
ComboBox {
    id: box
    property var choices: []
    property var current
    signal chosen(var value)

    model: choices
    textRole: "text"
    valueRole: "value"
    currentIndex: {
        for (let i = 0; i < choices.length; i++)
            if (choices[i].value === current) return i
        return -1
    }
    onActivated: (index) => box.chosen(box.choices[index].value)
    implicitHeight: 30
    implicitWidth: 150
    hoverEnabled: true
    focusPolicy: Qt.NoFocus
    font.pixelSize: 12

    background: Rectangle {
        radius: 8
        color: box.pressed ? Theme.surfacePressed : (box.hovered ? Theme.surfaceHover : Theme.surface)
        border.color: box.popup.visible ? Theme.accentStrong : Theme.border
        Behavior on color { ColorAnimation { duration: Theme.animFast } }
    }
    contentItem: Text {
        leftPadding: 10
        rightPadding: 26
        text: box.displayText
        color: Theme.text
        font.pixelSize: 12
        verticalAlignment: Text.AlignVCenter
        elide: Text.ElideRight
    }
    indicator: Icon {
        x: box.width - width - 9
        anchors.verticalCenter: box.verticalCenter
        iconName: "chevron-down"
        size: 14
        rotation: box.popup.visible ? 180 : 0
        Behavior on rotation { NumberAnimation { duration: Theme.anim; easing.type: Easing.OutCubic } }
    }
    delegate: ItemDelegate {
        required property var modelData
        required property int index
        width: ListView.view ? ListView.view.width : box.width
        height: 28
        highlighted: box.highlightedIndex === index
        hoverEnabled: true
        contentItem: Text {
            leftPadding: 4
            text: modelData.text
            color: modelData.value === box.current ? Theme.accent : Theme.text
            font.pixelSize: 12
            verticalAlignment: Text.AlignVCenter
            elide: Text.ElideRight
        }
        background: Rectangle {
            radius: 6
            color: parent.highlighted || parent.hovered ? Theme.surfaceHover : "transparent"
        }
    }
    popup: Popup {
        y: box.height + 4
        width: Math.max(box.width, 170)
        padding: 4
        implicitHeight: Math.min(contentItem.implicitHeight + 8, 340)
        enter: Transition { NumberAnimation { property: "opacity"; from: 0; to: 1; duration: Theme.animFast } }
        exit: Transition { NumberAnimation { property: "opacity"; from: 1; to: 0; duration: Theme.animFast } }
        contentItem: ListView {
            clip: true
            implicitHeight: contentHeight
            model: box.popup.visible ? box.delegateModel : null
            currentIndex: box.highlightedIndex
            boundsBehavior: Flickable.StopAtBounds
            ScrollIndicator.vertical: ScrollIndicator {}
        }
        background: Rectangle {
            radius: 10
            color: Theme.raised
            border.color: Theme.border
        }
    }
}
