import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Window

// The engraved pages on the desk; the notes that sound light up, a click on a bar jumps there
Item {
    id: view
    property real zoom: 1.0
    readonly property var result: controller.result
    readonly property var pages: result.pages || []
    readonly property real aspect: result.size ? result.size[1] / result.size[0] : 1.414
    readonly property real pageWidth: Math.min(Math.max(320, flick.width - 72), 1000) * zoom

    function zoomBy(factor) {
        const centre = (flick.contentY + flick.height / 2) / Math.max(1, flick.contentHeight)
        zoom = Math.max(0.4, Math.min(3.0, zoom * factor))
        controller.setPreference("zoom", zoom)
        flick.contentY = Math.max(0, centre * flick.contentHeight - flick.height / 2)
    }
    function fit() { zoom = 1.0; controller.setPreference("zoom", 1.0) }
    Component.onCompleted: zoom = controller.preferences.zoom || 1.0

    Rectangle { anchors.fill: parent; color: Theme.desk }

    Flickable {
        id: flick
        anchors.fill: parent
        contentWidth: Math.max(width, view.pageWidth + 72)
        contentHeight: pagesColumn.height + 64
        boundsBehavior: Flickable.StopAtBounds
        flickDeceleration: 4000
        maximumFlickVelocity: 4000
        clip: true
        ScrollBar.vertical: ScrollBar { }
        ScrollBar.horizontal: ScrollBar { policy: flick.contentWidth > flick.width ? ScrollBar.AsNeeded : ScrollBar.AlwaysOff }

        Behavior on contentY {
            id: scrollAnimation
            enabled: false
            NumberAnimation { duration: Theme.animSlow; easing.type: Easing.InOutCubic }
        }

        Column {
            id: pagesColumn
            y: 32
            x: (flick.contentWidth - width) / 2
            spacing: 28
            opacity: controller.busy ? 0.55 : 1
            Behavior on opacity { NumberAnimation { duration: Theme.anim } }

            Repeater {
                id: pageRepeater
                model: view.pages
                delegate: Item {
                    id: pageItem
                    required property int index
                    required property string modelData
                    width: view.pageWidth
                    height: view.pageWidth * view.aspect

                    // a soft shadow under the paper
                    Rectangle {
                        anchors.fill: paper
                        anchors.margins: -1
                        anchors.topMargin: 2
                        anchors.bottomMargin: -4
                        radius: 4
                        color: Theme.dark ? "#000000" : "#26000000"
                        opacity: Theme.dark ? 0.55 : 1
                    }
                    Rectangle {
                        id: paper
                        anchors.fill: parent
                        radius: 3
                        color: Theme.paper
                    }
                    // the bar being played
                    Rectangle {
                        readonly property var r: controller.measureRect
                        visible: player.playing && r.length === 5 && r[0] === pageItem.index
                        x: visible ? (r[1] * pageItem.width) - 4 : 0
                        y: visible ? (r[2] * pageItem.height) - 6 : 0
                        width: visible ? r[3] * pageItem.width + 8 : 0
                        height: visible ? r[4] * pageItem.height + 12 : 0
                        radius: 6
                        color: Qt.rgba(0.898, 0.282, 0.302, 0.07)
                        border.color: Qt.rgba(0.898, 0.282, 0.302, 0.22)
                    }
                    Image {
                        anchors.fill: parent
                        source: pageItem.modelData
                        sourceSize.width: Math.round(pageItem.width * Screen.devicePixelRatio)
                        asynchronous: true
                        cache: false
                        smooth: true
                        mipmap: true
                    }
                    // the notes that sound right now
                    Repeater {
                        model: controller.highlight
                        delegate: Rectangle {
                            required property var modelData
                            visible: modelData[0] === pageItem.index
                            x: modelData[1] * pageItem.width - 2
                            y: modelData[2] * pageItem.height - 2
                            width: modelData[3] * pageItem.width + 4
                            height: modelData[4] * pageItem.height + 4
                            radius: 4
                            color: Qt.rgba(0.898, 0.282, 0.302, 0.30)
                        }
                    }
                    TapHandler {
                        onTapped: (point) => controller.seekAt(pageItem.index, point.position.x / pageItem.width,
                                                               point.position.y / pageItem.height)
                    }
                    HoverHandler { cursorShape: Qt.PointingHandCursor }
                }
            }
        }

        WheelHandler {
            acceptedModifiers: Qt.ControlModifier
            onWheel: (event) => view.zoomBy(event.angleDelta.y > 0 ? 1.1 : 1 / 1.1)
        }
    }

    // keep the bar that is playing in sight
    Connections {
        target: controller
        function onScrollTo(page, fraction) {
            const item = pageRepeater.itemAt(page)
            if (!item || flick.moving || flick.dragging) return
            const y = pagesColumn.y + item.y + fraction * item.height
            const top = flick.contentY, bottom = flick.contentY + flick.height
            if (y < top + 40 || y > bottom - flick.height * 0.4) {
                scrollAnimation.enabled = true
                flick.contentY = Math.max(0, Math.min(flick.contentHeight - flick.height, y - flick.height * 0.25))
                scrollAnimation.enabled = false
            }
        }
    }

    // while the music is written again
    Rectangle {
        anchors { top: parent.top; horizontalCenter: parent.horizontalCenter; topMargin: 16 }
        width: busyRow.implicitWidth + 28
        height: 34
        radius: 17
        color: Theme.raised
        border.color: Theme.border
        opacity: controller.busy ? 1 : 0
        visible: opacity > 0
        Behavior on opacity { NumberAnimation { duration: Theme.anim } }
        Row {
            id: busyRow
            anchors.centerIn: parent
            spacing: 9
            Spinner { anchors.verticalCenter: parent.verticalCenter; width: 16; height: 16 }
            Text { anchors.verticalCenter: parent.verticalCenter; text: controller.tr.updating; color: Theme.text; font.pixelSize: 12 }
        }
    }
}
