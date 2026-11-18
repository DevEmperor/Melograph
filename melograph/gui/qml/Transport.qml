import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import Melograph

// Play the recording, the written notes or both, and see where you are
Rectangle {
    id: transport
    readonly property var tr: controller.tr
    implicitHeight: 74
    color: Theme.panel

    function clock(seconds) {
        seconds = Math.max(0, Math.floor(seconds))
        return Math.floor(seconds / 60) + ":" + String(seconds % 60).padStart(2, "0")
    }

    Rectangle { anchors { left: parent.left; right: parent.right; top: parent.top } height: 1; color: Theme.border }

    RowLayout {
        anchors.fill: parent
        anchors.leftMargin: 16
        anchors.rightMargin: 16
        spacing: 14

        PlayButton {
            playing: player.playing
            enabled: player.originalReady || player.scoreReady
            onClicked: player.toggle()
            ToolTip.visible: hovered
            ToolTip.delay: 600
            ToolTip.text: player.playing ? transport.tr.pause : transport.tr.play
        }

        Text {
            Layout.preferredWidth: 86
            text: transport.clock(player.position) + " / " + transport.clock(Math.max(player.duration, controller.duration))
            color: Theme.textDim
            font.pixelSize: 12
            font.features: { "tnum": 1 }
        }

        // the recording as a waveform: click or drag to move
        Item {
            Layout.fillWidth: true
            Layout.fillHeight: true
            Layout.topMargin: 14
            Layout.bottomMargin: 14
            Waveform {
                id: wave
                anchors.fill: parent
                peaks: controller.peaks
                duration: Math.max(player.duration, controller.duration)
                position: player.position
                bars: controller.result.bars || []
                color: Theme.dark ? "#3d363f" : "#d6cfd3"
                playedColor: Theme.accentStrong
            }
            Rectangle {
                visible: controller.peaks.length === 0
                anchors.verticalCenter: parent.verticalCenter
                width: parent.width
                height: 4
                radius: 2
                color: Theme.surfaceHover
                Rectangle {
                    width: parent.width * (player.position / Math.max(0.001, wave.duration))
                    height: parent.height
                    radius: 2
                    color: Theme.accentStrong
                }
            }
            MouseArea {
                anchors.fill: parent
                cursorShape: Qt.PointingHandCursor
                function seekTo(x) { player.seek(Math.max(0, Math.min(1, x / width)) * wave.duration) }
                onPressed: (mouse) => seekTo(mouse.x)
                onPositionChanged: (mouse) => { if (pressed) seekTo(mouse.x) }
            }
        }

        Segments {
            value: player.mode
            options: [
                { text: transport.tr.mode_original, value: "original", enabled: controller.hasAudio },
                { text: transport.tr.mode_score, value: "score" },
                { text: transport.tr.mode_both, value: "both", enabled: controller.hasAudio },
            ]
            onChosen: (value) => { player.mode = value; controller.setPreference("mode", value) }
            ToolTip.visible: modeHover.hovered
            ToolTip.delay: 900
            ToolTip.text: transport.tr.mode_tip
            HoverHandler { id: modeHover }
            Spinner {
                anchors { right: parent.right; top: parent.top; margins: -5 }
                width: 12
                height: 12
                lineWidth: 1.8
                visible: player.mode !== "original" && !player.scoreReady
            }
        }

        IconButton {
            iconName: "follow"
            active: controller.preferences.follow
            tip: transport.tr.follow_tip
            onClicked: controller.setPreference("follow", !controller.preferences.follow)
        }

        Row {
            spacing: 4
            Icon { anchors.verticalCenter: parent.verticalCenter; iconName: "volume"; size: 17 }
            Slider {
                id: volume
                anchors.verticalCenter: parent.verticalCenter
                width: 86
                from: 0
                to: 1
                value: player.volume
                onMoved: player.volume = value
                onPressedChanged: if (!pressed) controller.setPreference("volume", value)
                background: Rectangle {
                    x: volume.leftPadding
                    y: volume.topPadding + volume.availableHeight / 2 - height / 2
                    width: volume.availableWidth
                    height: 4
                    radius: 2
                    color: Theme.surfacePressed
                    Rectangle { width: volume.visualPosition * parent.width; height: parent.height; radius: 2; color: Theme.textDim }
                }
                handle: Rectangle {
                    x: volume.leftPadding + volume.visualPosition * (volume.availableWidth - width)
                    y: volume.topPadding + volume.availableHeight / 2 - height / 2
                    width: 12
                    height: 12
                    radius: 6
                    color: volume.pressed ? Theme.accent : Theme.text
                }
            }
        }
    }
}
