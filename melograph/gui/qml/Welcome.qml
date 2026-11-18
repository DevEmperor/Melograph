import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import QtQuick.Shapes

// Start page: drop a recording, open or record one, or pick a recent piece
Item {
    id: welcome
    property bool dragActive: false
    signal openRequested()
    signal recordRequested()
    readonly property var tr: controller.tr

    Flickable {
        id: flick
        anchors.fill: parent
        contentWidth: width
        contentHeight: column.implicitHeight + 80
        boundsBehavior: Flickable.StopAtBounds
        ScrollBar.vertical: ScrollBar { policy: flick.contentHeight > flick.height ? ScrollBar.AsNeeded : ScrollBar.AlwaysOff }

        ColumnLayout {
            id: column
            width: Math.min(760, flick.width - 64)
            x: (flick.width - width) / 2
            y: Math.max(40, (flick.height - implicitHeight) / 2 - 20)
            spacing: 0

            Image {
                Layout.alignment: Qt.AlignHCenter
                source: "icons/app.svg"
                sourceSize: Qt.size(72, 72)
            }
            Text {
                Layout.alignment: Qt.AlignHCenter
                Layout.topMargin: 18
                text: welcome.tr.welcome_title
                color: Theme.text
                font.pixelSize: 30
                font.weight: Font.DemiBold
                font.letterSpacing: -0.3
            }
            Text {
                Layout.alignment: Qt.AlignHCenter
                Layout.topMargin: 10
                Layout.maximumWidth: 560
                horizontalAlignment: Text.AlignHCenter
                wrapMode: Text.WordWrap
                text: welcome.tr.welcome_text
                color: Theme.textDim
                font.pixelSize: 14
                lineHeight: 1.25
            }

            // ── the drop zone ─────────────────────────────────────────────
            Rectangle {
                id: zone
                Layout.fillWidth: true
                Layout.topMargin: 30
                Layout.preferredHeight: 214
                radius: 20
                color: welcome.dragActive ? Theme.accentSoft : (zoneHover.hovered ? Theme.surfaceHover : Theme.surface)
                Behavior on color { ColorAnimation { duration: Theme.anim } }
                scale: welcome.dragActive ? 1.015 : 1
                Behavior on scale { NumberAnimation { duration: Theme.anim; easing.type: Easing.OutCubic } }
                HoverHandler { id: zoneHover }
                TapHandler { onTapped: welcome.openRequested() }

                Shape {
                    anchors.fill: parent
                    ShapePath {
                        strokeColor: welcome.dragActive ? Theme.accentStrong : Theme.border
                        strokeWidth: 1.6
                        strokeStyle: ShapePath.DashLine
                        dashPattern: [5, 4]
                        fillColor: "transparent"
                        startX: zone.radius; startY: 0.8
                        PathLine { x: zone.width - zone.radius; y: 0.8 }
                        PathArc { x: zone.width - 0.8; y: zone.radius; radiusX: zone.radius - 0.8; radiusY: zone.radius - 0.8 }
                        PathLine { x: zone.width - 0.8; y: zone.height - zone.radius }
                        PathArc { x: zone.width - zone.radius; y: zone.height - 0.8; radiusX: zone.radius - 0.8; radiusY: zone.radius - 0.8 }
                        PathLine { x: zone.radius; y: zone.height - 0.8 }
                        PathArc { x: 0.8; y: zone.height - zone.radius; radiusX: zone.radius - 0.8; radiusY: zone.radius - 0.8 }
                        PathLine { x: 0.8; y: zone.radius }
                        PathArc { x: zone.radius; y: 0.8; radiusX: zone.radius - 0.8; radiusY: zone.radius - 0.8 }
                    }
                }

                ColumnLayout {
                    anchors.centerIn: parent
                    spacing: 0
                    Rectangle {
                        Layout.alignment: Qt.AlignHCenter
                        width: 54
                        height: 54
                        radius: 27
                        color: Theme.accentSoft
                        Icon {
                            anchors.centerIn: parent
                            iconName: welcome.dragActive ? "download" : "wave"
                            size: 26
                            color: Theme.accent
                        }
                    }
                    Text {
                        Layout.alignment: Qt.AlignHCenter
                        Layout.topMargin: 14
                        text: welcome.dragActive ? welcome.tr.drop_release : welcome.tr.drop_here
                        color: Theme.text
                        font.pixelSize: 17
                        font.weight: Font.DemiBold
                    }
                    Text {
                        Layout.alignment: Qt.AlignHCenter
                        Layout.topMargin: 4
                        text: welcome.tr.formats
                        color: Theme.textFaint
                        font.pixelSize: 12
                    }
                    Row {
                        Layout.alignment: Qt.AlignHCenter
                        Layout.topMargin: 18
                        spacing: 10
                        TextButton {
                            large: true
                            emphasized: true
                            iconName: "folder"
                            text: welcome.tr.open_file
                            onClicked: welcome.openRequested()
                        }
                        TextButton {
                            large: true
                            iconName: "mic"
                            text: welcome.tr.record
                            onClicked: welcome.recordRequested()
                        }
                    }
                }
            }

            // ── recent pieces ─────────────────────────────────────────────
            Text {
                visible: controller.recent.length > 0
                Layout.topMargin: 34
                text: welcome.tr.recent.toUpperCase()
                color: Theme.textFaint
                font.pixelSize: 11
                font.letterSpacing: 1.1
                font.weight: Font.DemiBold
            }
            Flow {
                visible: controller.recent.length > 0
                Layout.fillWidth: true
                Layout.topMargin: 10
                spacing: 12
                Repeater {
                    model: controller.recent.slice(0, 9)
                    delegate: RecentCard {
                        width: (column.width - 24) / 3
                        entry: modelData
                    }
                }
            }
        }
    }

    component RecentCard: AbstractButton {
        id: card
        property var entry
        implicitHeight: 162
        hoverEnabled: true
        focusPolicy: Qt.NoFocus
        enabled: entry.exists
        opacity: entry.exists ? 1 : 0.5
        onClicked: controller.openFile(entry.path)

        background: Rectangle {
            radius: 14
            color: card.hovered ? Theme.surfaceHover : Theme.surface
            border.color: card.hovered ? Qt.rgba(0.898, 0.282, 0.302, 0.45) : Theme.border
            Behavior on color { ColorAnimation { duration: Theme.animFast } }
            Behavior on border.color { ColorAnimation { duration: Theme.animFast } }
        }
        contentItem: ColumnLayout {
            spacing: 0
            Rectangle {
                Layout.fillWidth: true
                Layout.preferredHeight: 96
                Layout.margins: 6
                radius: 9
                color: Theme.paper
                clip: true
                Image {
                    anchors.fill: parent
                    source: card.entry.thumb || ""
                    fillMode: Image.PreserveAspectCrop
                    verticalAlignment: Image.AlignTop
                    smooth: true
                    asynchronous: true
                    opacity: Theme.dark ? 0.94 : 1
                }
                Icon {
                    visible: !card.entry.thumb
                    anchors.centerIn: parent
                    iconName: "score"
                    size: 30
                    color: "#b8b0b8"
                }
            }
            Text {
                Layout.fillWidth: true
                Layout.leftMargin: 12
                Layout.rightMargin: 12
                Layout.topMargin: 4
                text: card.entry.title || card.entry.path.split("/").pop()
                color: Theme.text
                font.pixelSize: 13
                font.weight: Font.DemiBold
                elide: Text.ElideRight
            }
            Text {
                Layout.fillWidth: true
                Layout.leftMargin: 12
                Layout.rightMargin: 12
                Layout.topMargin: 2
                text: card.entry.exists
                      ? [card.entry.meter, controller.language === "de" ? card.entry.keyDe : card.entry.keyEn,
                         controller.tr.bars_count.replace("%1", card.entry.bars)].join(" · ")
                      : controller.tr.missing_file
                color: Theme.textFaint
                font.pixelSize: 12
                elide: Text.ElideRight
            }
            Item { Layout.fillHeight: true }
        }
        IconButton {
            anchors { top: parent.top; right: parent.right; margins: 10 }
            visible: card.hovered || !card.entry.exists
            enabled: true
            iconName: "close"
            iconSize: 14
            implicitWidth: 26
            implicitHeight: 26
            tip: controller.tr.remove
            background: Rectangle { radius: 13; color: Theme.dark ? "#cc1c181d" : "#ccffffff" }
            onClicked: controller.forget(card.entry.path)
        }
    }
}
