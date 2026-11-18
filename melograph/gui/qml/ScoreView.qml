import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Window

// The engraved pages side by side on the desk, as in MuseScore. The notes that sound light up,
// a click on a bar jumps there. Zoom: Ctrl+wheel, pinch on the touchpad, Ctrl+plus/minus.
Item {
    id: view
    property real zoom: 1.0  // 1 = a whole page fills the height of the view
    readonly property real minZoom: 0.35
    readonly property real maxZoom: 4.0
    readonly property var result: controller.result
    readonly property var pages: result.pages || []
    readonly property real aspect: result.size ? result.size[1] / result.size[0] : 1.414
    readonly property real margin: 28
    readonly property real gap: 32
    readonly property real fitHeight: Math.max(240, flick.height - 2 * margin)
    readonly property real pageHeight: fitHeight * zoom
    readonly property real pageWidth: pageHeight / aspect
    readonly property real wheelStep: 144  // pixels per notch of the mouse wheel (Qt's own is 72)
    readonly property real touchpadSpeed: 2
    // Pages are drawn at a few fixed sizes only, so that zooming does not redraw them at every
    // step; in between they are scaled smoothly.
    readonly property real rasterWidth: Math.min(4096, fitHeight / aspect * Screen.devicePixelRatio
                                                 * Math.pow(Math.SQRT2, Math.ceil(Math.log(Math.max(zoom, 0.5)) / Math.log(Math.SQRT2))))

    function clampX(x) { return Math.max(0, Math.min(flick.contentWidth - flick.width, x)) }
    function clampY(y) { return Math.max(0, Math.min(flick.contentHeight - flick.height, y)) }

    // Zoom so that the point (px, py) of the view stays where it is.
    function zoomAt(factor, px, py) {
        const before = zoom
        const after = Math.max(minZoom, Math.min(maxZoom, before * factor))
        if (Math.abs(after - before) < 0.0001) return
        glideX.stop(); glideY.stop()
        const cx = flick.contentX + px - pagesRow.x
        const cy = flick.contentY + py - pagesRow.y
        zoom = after
        const ratio = after / before
        flick.contentX = clampX(cx * ratio + pagesRow.x - px)
        flick.contentY = clampY(cy * ratio + pagesRow.y - py)
        saveZoom.restart()
    }
    function zoomBy(factor) { zoomAt(factor, flick.width / 2, flick.height / 2) }
    function fit() {
        const centre = (flick.contentX + flick.width / 2 - pagesRow.x) / Math.max(1, pagesRow.width)
        zoom = 1.0
        flick.contentY = 0
        flick.contentX = clampX(centre * pagesRow.width + pagesRow.x - flick.width / 2)
        saveZoom.restart()
    }
    // Scroll by (dx, dy). Pages stand side by side: while a page fits the height, the wheel turns them sideways.
    function scrollBy(dx, dy, smooth) {
        if (flick.contentHeight <= flick.height + 1 && dx === 0) {
            dx = dy
            dy = 0
        }
        const fromX = glideX.running ? glideX.to : flick.contentX
        const fromY = glideY.running ? glideY.to : flick.contentY
        glide(clampX(fromX + dx), clampY(fromY + dy), smooth ? 160 : 0)
    }
    function glide(x, y, duration) {
        glideX.stop(); glideY.stop()
        if (duration <= 0) {
            flick.contentX = x
            flick.contentY = y
            return
        }
        glideX.duration = glideY.duration = duration
        glideX.from = flick.contentX; glideX.to = x
        glideY.from = flick.contentY; glideY.to = y
        glideX.start(); glideY.start()
    }
    Component.onCompleted: zoom = Math.max(minZoom, Math.min(maxZoom, controller.preferences.zoom || 1.0))

    Timer { id: saveZoom; interval: 400; onTriggered: controller.setPreference("zoom", view.zoom) }
    NumberAnimation { id: glideX; target: flick; property: "contentX"; easing.type: Easing.OutCubic }
    NumberAnimation { id: glideY; target: flick; property: "contentY"; easing.type: Easing.OutCubic }

    Rectangle { anchors.fill: parent; color: Theme.desk }

    Flickable {
        id: flick
        objectName: "scoreFlick"
        anchors.fill: parent
        contentWidth: Math.max(width, pagesRow.width + 2 * view.margin)
        contentHeight: Math.max(height, pagesRow.height + 2 * view.margin)
        boundsBehavior: Flickable.StopAtBounds
        flickDeceleration: 3000
        maximumFlickVelocity: 6000
        clip: true
        ScrollBar.vertical: ScrollBar { policy: flick.contentHeight > flick.height + 1 ? ScrollBar.AsNeeded : ScrollBar.AlwaysOff }
        ScrollBar.horizontal: ScrollBar { policy: flick.contentWidth > flick.width + 1 ? ScrollBar.AsNeeded : ScrollBar.AlwaysOff }

        // Laid out by hand rather than with a Row, so that the sizes are right at once when zooming.
        Item {
            id: pagesRow
            x: (flick.contentWidth - width) / 2
            y: (flick.contentHeight - height) / 2
            width: view.pages.length * view.pageWidth + Math.max(0, view.pages.length - 1) * view.gap
            height: view.pageHeight
            opacity: controller.busy ? 0.55 : 1
            Behavior on opacity { NumberAnimation { duration: Theme.anim } }

            Repeater {
                id: pageRepeater
                model: view.pages
                delegate: Item {
                    id: pageItem
                    required property int index
                    required property string modelData
                    // on screen or close to it: only these get a sharp copy when zoomed in
                    readonly property bool near: pagesRow.x + x + width > flick.contentX - flick.width
                                                 && pagesRow.x + x < flick.contentX + 2 * flick.width
                    x: index * (view.pageWidth + view.gap)
                    width: view.pageWidth
                    height: view.pageHeight

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
                    // The page at the size of a whole page on screen; it stays visible underneath
                    // while a sharper copy for the current zoom is drawn.
                    Image {
                        anchors.fill: parent
                        visible: !sharp.visible  // under the sharp copy its blur would thicken every line
                        source: pageItem.modelData
                        sourceSize.width: Math.round(view.fitHeight / view.aspect * Screen.devicePixelRatio)
                        asynchronous: true
                        cache: false
                        smooth: true
                        mipmap: true
                    }
                    Image {
                        id: sharp
                        anchors.fill: parent
                        visible: view.zoom > 1.05 && pageItem.near && status === Image.Ready
                        source: view.zoom > 1.05 && pageItem.near ? pageItem.modelData : ""
                        sourceSize.width: Math.round(view.rasterWidth)
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


        // The wheel: Ctrl zooms where the pointer is, Shift scrolls sideways, a touchpad scrolls
        // in both directions. Twice as far per step as Qt would scroll on its own.
        // (A MouseArea, because it is given every wheel event: a WheelHandler takes those of a
        // mouse only and leaves out a touchpad – two fingers with Ctrl then did nothing at all.)
        MouseArea {
            parent: flick
            anchors.fill: parent
            acceptedButtons: Qt.NoButton
            onWheel: (wheel) => {
                const touchpad = wheel.pixelDelta.x !== 0 || wheel.pixelDelta.y !== 0
                if (wheel.modifiers & Qt.ControlModifier) {
                    // one notch of a wheel, or about 50 pixels of finger travel, is one step
                    const turned = touchpad ? (wheel.pixelDelta.y || wheel.pixelDelta.x) / 50
                                            : (wheel.angleDelta.y || wheel.angleDelta.x) / 120
                    if (turned !== 0) view.zoomAt(Math.pow(1.12, turned), wheel.x, wheel.y)
                    return
                }
                let dx = touchpad ? -wheel.pixelDelta.x * view.touchpadSpeed : -wheel.angleDelta.x / 120 * view.wheelStep
                let dy = touchpad ? -wheel.pixelDelta.y * view.touchpadSpeed : -wheel.angleDelta.y / 120 * view.wheelStep
                if ((wheel.modifiers & Qt.ShiftModifier) && dx === 0) {
                    dx = dy
                    dy = 0
                }
                view.scrollBy(dx, dy, !touchpad)
            }
        }
        // two fingers apart and together on a touchpad or a touch screen
        PinchHandler {
            parent: flick
            target: null
            property real startZoom: 1
            property real applied: 1
            onActiveChanged: if (active) { startZoom = view.zoom; applied = 1 }
            onActiveScaleChanged: {
                if (!active) return
                view.zoomAt(activeScale / applied, centroid.position.x, centroid.position.y)
                applied = activeScale
            }
        }
    }

    // keep the bar that is playing in sight
    Connections {
        target: controller
        function onScrollTo(page, fx, fy) {
            const item = pageRepeater.itemAt(page)
            if (!item || flick.dragging || flick.flicking) return
            const x = pagesRow.x + item.x + fx * item.width
            const y = pagesRow.y + item.y + fy * item.height
            let tx = flick.contentX
            let ty = flick.contentY
            if (x < tx + 60 || x > tx + flick.width * 0.78) tx = x - flick.width * 0.18
            if (flick.contentHeight > flick.height + 1 && (y < ty + 40 || y > ty + flick.height * 0.6)) ty = y - flick.height * 0.25
            if (tx !== flick.contentX || ty !== flick.contentY) view.glide(view.clampX(tx), view.clampY(ty), Theme.animSlow)
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
