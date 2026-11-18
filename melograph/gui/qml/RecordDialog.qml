import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts

// Record straight from the microphone; when done, the recording is turned into music
Popup {
    id: dialog
    readonly property var tr: controller.tr
    anchors.centerIn: Overlay.overlay
    width: 440
    padding: 24
    modal: true
    focus: true
    closePolicy: recorder.recording ? Popup.NoAutoClose : (Popup.CloseOnEscape | Popup.CloseOnPressOutside)
    Overlay.modal: Rectangle { color: Theme.dark ? "#99000000" : "#55000000" }
    enter: Transition {
        NumberAnimation { property: "opacity"; from: 0; to: 1; duration: Theme.anim }
        NumberAnimation { property: "scale"; from: 0.97; to: 1; duration: Theme.anim; easing.type: Easing.OutCubic }
    }
    exit: Transition { NumberAnimation { property: "opacity"; from: 1; to: 0; duration: Theme.animFast } }
    background: Rectangle { radius: 16; color: Theme.raised; border.color: Theme.border }

    function clock(seconds) {
        seconds = Math.floor(seconds)
        return Math.floor(seconds / 60) + ":" + String(seconds % 60).padStart(2, "0")
    }

    contentItem: ColumnLayout {
        spacing: 14
        Text { text: dialog.tr.rec_title; color: Theme.text; font.pixelSize: 18; font.weight: Font.DemiBold }
        Text {
            Layout.fillWidth: true
            text: dialog.tr.rec_hint
            color: Theme.textDim
            font.pixelSize: 13
            wrapMode: Text.WordWrap
        }

        // the big round light, breathing with the sound
        Item {
            Layout.fillWidth: true
            Layout.preferredHeight: 150
            Rectangle {
                anchors.centerIn: parent
                width: 76 + recorder.level * 70
                height: width
                radius: width / 2
                color: Theme.accentSoft
                visible: recorder.recording
                Behavior on width { NumberAnimation { duration: 90 } }
            }
            Rectangle {
                anchors.centerIn: parent
                width: 76
                height: 76
                radius: 38
                color: recorder.recording ? Theme.accentStrong : Theme.surfaceHover
                Behavior on color { ColorAnimation { duration: Theme.anim } }
                Icon { anchors.centerIn: parent; iconName: "mic"; size: 30; color: recorder.recording ? "#ffffff" : Theme.textDim }
            }
        }
        Text {
            Layout.alignment: Qt.AlignHCenter
            text: dialog.clock(recorder.elapsed)
            color: recorder.recording ? Theme.text : Theme.textFaint
            font.pixelSize: 22
            font.features: { "tnum": 1 }
        }
        Text {
            Layout.fillWidth: true
            horizontalAlignment: Text.AlignHCenter
            text: dialog.tr.rec_saved_in.replace("%1", controller.recordFolder)
            color: Theme.textFaint
            font.pixelSize: 11
            elide: Text.ElideMiddle
        }
        RowLayout {
            Layout.alignment: Qt.AlignHCenter
            spacing: 10
            TextButton {
                text: recorder.recording ? dialog.tr.rec_discard : dialog.tr.close
                onClicked: { recorder.cancel(); dialog.close() }
            }
            TextButton {
                large: true
                emphasized: true
                iconName: recorder.recording ? "check" : "mic"
                text: recorder.recording ? dialog.tr.rec_stop : dialog.tr.rec_start
                onClicked: {
                    if (recorder.recording) {
                        recorder.stop(controller.recordFolder)
                        dialog.close()
                    } else {
                        recorder.start()
                    }
                }
            }
        }
    }
}
