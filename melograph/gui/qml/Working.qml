import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import Melograph

// While Melograph listens: the steps, the progress, and the recording being scanned
Item {
    id: working
    readonly property var tr: controller.tr
    readonly property var active: {
        for (const s of controller.stages) if (s.state === "active") return s
        return null
    }

    ColumnLayout {
        anchors.centerIn: parent
        width: Math.min(560, parent.width - 64)
        spacing: 0

        Text {
            Layout.alignment: Qt.AlignHCenter
            text: working.tr.working_title
            color: Theme.text
            font.pixelSize: 24
            font.weight: Font.DemiBold
        }
        Text {
            Layout.alignment: Qt.AlignHCenter
            Layout.topMargin: 6
            Layout.maximumWidth: parent.width
            text: controller.fileName
            color: Theme.textDim
            font.pixelSize: 13
            elide: Text.ElideMiddle
        }

        // The recording, lit up as far as Melograph has got
        Item {
            Layout.fillWidth: true
            Layout.preferredHeight: 64
            Layout.topMargin: 26
            Waveform {
                id: wave
                anchors.fill: parent
                peaks: controller.peaks
                duration: 1
                position: working.active && working.active.key === "transcribe" ? controller.progress
                          : (working.active && (working.active.key === "beats" || working.active.key === "score") ? 1 : 0)
                color: Theme.dark ? "#3a333c" : "#d9d2d6"
                playedColor: Theme.accentStrong
                Behavior on position { NumberAnimation { duration: 600; easing.type: Easing.OutCubic } }
            }
            Rectangle {
                visible: controller.peaks.length === 0
                anchors.centerIn: parent
                width: parent.width
                height: 2
                radius: 1
                color: Theme.surfaceHover
            }
        }

        // The steps
        Rectangle {
            Layout.fillWidth: true
            Layout.topMargin: 24
            implicitHeight: steps.implicitHeight + 24
            radius: 16
            color: Theme.surface
            border.color: Theme.border

            ColumnLayout {
                id: steps
                anchors { left: parent.left; right: parent.right; top: parent.top; margins: 12 }
                spacing: 2
                Repeater {
                    model: controller.stages
                    delegate: ColumnLayout {
                        Layout.fillWidth: true
                        spacing: 0
                        RowLayout {
                            Layout.fillWidth: true
                            Layout.preferredHeight: 36
                            spacing: 12
                            Item {
                                Layout.preferredWidth: 22
                                Layout.preferredHeight: 22
                                Spinner {
                                    anchors.centerIn: parent
                                    visible: modelData.state === "active"
                                }
                                Rectangle {
                                    anchors.centerIn: parent
                                    visible: modelData.state === "done"
                                    width: 20
                                    height: 20
                                    radius: 10
                                    color: Theme.accentSoft
                                    Icon { anchors.centerIn: parent; iconName: "check"; size: 14; color: Theme.accent }
                                }
                                Rectangle {
                                    anchors.centerIn: parent
                                    visible: modelData.state === "pending"
                                    width: 8
                                    height: 8
                                    radius: 4
                                    color: Theme.surfacePressed
                                }
                            }
                            Text {
                                Layout.fillWidth: true
                                text: modelData.label
                                color: modelData.state === "pending" ? Theme.textFaint : Theme.text
                                font.pixelSize: 14
                                font.weight: modelData.state === "active" ? Font.DemiBold : Font.Normal
                            }
                            Text {
                                visible: modelData.state === "active" && modelData.detail.length > 0
                                text: modelData.detail
                                color: Theme.textFaint
                                font.pixelSize: 12
                            }
                            Text {
                                visible: modelData.state === "active" && modelData.key === "transcribe" && controller.progress > 0
                                text: Math.round(controller.progress * 100) + " %"
                                color: Theme.textDim
                                font.pixelSize: 13
                                font.features: { "tnum": 1 }
                            }
                        }
                        // thin progress line under the step that is running
                        Rectangle {
                            visible: modelData.state === "active" && modelData.key === "transcribe"
                            Layout.fillWidth: true
                            Layout.leftMargin: 34
                            Layout.preferredHeight: 3
                            radius: 1.5
                            color: Theme.surfaceHover
                            Rectangle {
                                width: parent.width * controller.progress
                                height: parent.height
                                radius: 1.5
                                color: Theme.accentStrong
                                Behavior on width { NumberAnimation { duration: 500; easing.type: Easing.OutCubic } }
                            }
                        }
                        Text {
                            visible: modelData.state === "active" && modelData.key === "transcribe" && controller.remaining.length > 0
                            Layout.leftMargin: 34
                            Layout.topMargin: 5
                            Layout.bottomMargin: 4
                            text: controller.remaining + "  ·  " + (controller.device === "cuda" ? working.tr.on_gpu : working.tr.on_cpu)
                            color: Theme.textFaint
                            font.pixelSize: 12
                        }
                    }
                }
            }
        }

        TextButton {
            Layout.alignment: Qt.AlignHCenter
            Layout.topMargin: 22
            text: working.tr.cancel
            iconName: "close"
            onClicked: controller.cancel()
        }
    }
}
