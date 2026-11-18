import QtQuick
import QtQuick.Controls.Basic
import Melograph

// What was heard, on a keyboard grid: scroll sideways with the wheel, zoom with Ctrl+wheel
Item {
    id: rollView
    readonly property real total: Math.max(controller.duration, 1)

    function zoomBy(factor) {
        const centre = roll.viewStart + roll.viewSpan / 2
        roll.viewSpan = Math.max(2, Math.min(rollView.total + 2, roll.viewSpan / factor))
        roll.viewStart = Math.max(0, centre - roll.viewSpan / 2)
    }

    Rectangle { anchors.fill: parent; color: Theme.panel }

    PianoRoll {
        id: roll
        anchors.fill: parent
        anchors.bottomMargin: 10
        notes: controller.result.roll || []
        bars: controller.result.bars || []
        position: player.position
        dark: Theme.dark
        viewSpan: Math.min(12, rollView.total + 1)
        Component.onCompleted: viewStart = Math.max(0, player.position - 2)
    }

    // follow the playback
    Connections {
        target: player
        function onPositionChanged() {
            if (!player.playing || !controller.preferences.follow) return
            const p = player.position
            if (p > roll.viewStart + roll.viewSpan * 0.85 || p < roll.viewStart)
                roll.viewStart = Math.max(0, p - roll.viewSpan * 0.15)
        }
    }

    // Wheel and touchpad (a MouseArea is given every wheel event, a WheelHandler only those of a mouse)
    MouseArea {
        anchors.fill: parent
        acceptedButtons: Qt.NoButton
        onWheel: (wheel) => {
            const touchpad = wheel.pixelDelta.x !== 0 || wheel.pixelDelta.y !== 0
            if (wheel.modifiers & Qt.ControlModifier) {
                const turned = touchpad ? (wheel.pixelDelta.y || wheel.pixelDelta.x) / 50
                                        : (wheel.angleDelta.y || wheel.angleDelta.x) / 120
                if (turned !== 0) rollView.zoomBy(Math.pow(1.15, turned))
                return
            }
            // a notch moves a sixth of the view; a touchpad moves twice as far as the fingers
            let seconds
            if (touchpad) {
                const pixels = wheel.pixelDelta.x !== 0 ? wheel.pixelDelta.x : wheel.pixelDelta.y
                seconds = pixels * 2 / Math.max(1, roll.width - 34) * roll.viewSpan
            } else {
                seconds = (wheel.angleDelta.x !== 0 ? wheel.angleDelta.x : wheel.angleDelta.y) / 120 * roll.viewSpan * 0.16
            }
            roll.viewStart = Math.max(0, Math.min(rollView.total - roll.viewSpan * 0.5, roll.viewStart - seconds))
        }
    }
    PinchHandler {
        target: null
        property real applied: 1
        onActiveChanged: if (active) applied = 1
        onActiveScaleChanged: {
            if (!active) return
            rollView.zoomBy(activeScale / applied)
            applied = activeScale
        }
    }
    DragHandler {
        target: null
        property real startView: 0
        onActiveChanged: if (active) startView = roll.viewStart
        onTranslationChanged: roll.viewStart = Math.max(0, startView - translation.x / (roll.width - 34) * roll.viewSpan)
    }
    TapHandler {
        onTapped: (point) => player.seek(roll.viewStart + (point.position.x - 34) / (roll.width - 34) * roll.viewSpan)
    }

    // where the view stands in the whole piece
    Rectangle {
        anchors { left: parent.left; right: parent.right; bottom: parent.bottom; leftMargin: 34 }
        height: 4
        color: Theme.surface
        Rectangle {
            x: roll.viewStart / rollView.total * parent.width
            width: Math.max(12, roll.viewSpan / rollView.total * parent.width)
            height: parent.height
            radius: 2
            color: Theme.surfacePressed
        }
    }
}
