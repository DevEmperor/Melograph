import QtQuick

// A turning arc for work in progress
Item {
    id: spinner
    property color color: Theme.accent
    property real lineWidth: 2.2
    property bool running: visible
    implicitWidth: 18
    implicitHeight: 18

    Canvas {
        id: arc
        anchors.fill: parent
        onPaint: {
            const ctx = getContext("2d")
            ctx.reset()
            ctx.lineWidth = spinner.lineWidth
            ctx.lineCap = "round"
            ctx.strokeStyle = spinner.color
            const r = Math.min(width, height) / 2 - spinner.lineWidth
            ctx.beginPath()
            ctx.arc(width / 2, height / 2, r, 0, Math.PI * 1.45)
            ctx.stroke()
        }
        Component.onCompleted: requestPaint()
    }
    RotationAnimator on rotation {
        running: spinner.running
        from: 0
        to: 360
        duration: 900
        loops: Animation.Infinite
    }
    onColorChanged: arc.requestPaint()
}
