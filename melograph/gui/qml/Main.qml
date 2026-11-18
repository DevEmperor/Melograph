import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Dialogs
import QtQuick.Layouts

// The main window: frameless like QuickBible; start page, listening, and the score with its player
Window {
    id: window
    width: controller.preferences.windowWidth
    height: controller.preferences.windowHeight
    minimumWidth: 900
    minimumHeight: 580
    visible: true
    flags: Qt.Window | Qt.FramelessWindowHint
    color: "transparent"
    title: controller.fileName ? (controller.options.title || controller.fileName) + " – Melograph" : "Melograph"

    readonly property var tr: controller.tr
    readonly property bool maximized: visibility === Window.Maximized || visibility === Window.FullScreen
    property bool fillsScreen: false  // set by app.py
    readonly property bool squareCorners: maximized || fillsScreen
    readonly property bool onScore: controller.page === "score"
    property bool dragActive: false

    palette.toolTipBase: Theme.dark ? "#1c191d" : "#ffffff"
    palette.toolTipText: Theme.text

    Component.onCompleted: if (controller.preferences.windowMaximized) window.visibility = Window.Maximized
    onWidthChanged: geometryTimer.restart()
    onHeightChanged: geometryTimer.restart()
    onVisibilityChanged: geometryTimer.restart()
    Timer {
        id: geometryTimer
        interval: 800
        onTriggered: if (window.visibility === Window.Windowed || window.visibility === Window.Maximized)
                         controller.rememberWindow(window.width, window.height, window.visibility === Window.Maximized)
    }

    function openDialog() { openFile.open() }
    function exportAs(kind, extension) {
        saveFile.kind = kind
        saveFile.nameFilters = [extension.toUpperCase() + " (*." + extension + ")"]
        saveFile.selectedFile = controller.suggestedFile(extension)
        saveFile.open()
    }
    function toggleSidebar() { controller.setPreference("sidebar", !controller.preferences.sidebar) }
    function zoomBy(f) { if (scoreView.visible) scoreView.zoomBy(f); else if (rollView.visible) rollView.zoomBy(f) }

    // ── keyboard ───────────────────────────────────────────────────────────
    Shortcut { sequences: [StandardKey.Open]; onActivated: window.openDialog() }
    Shortcut { sequence: "Ctrl+Q"; onActivated: window.close() }
    Shortcut { sequence: "Ctrl+R"; onActivated: recordDialog.open() }
    Shortcut { sequence: "Ctrl+,"; onActivated: preferences.open() }
    Shortcut { sequence: "F11"; onActivated: window.visibility === Window.FullScreen ? window.showNormal() : window.showFullScreen() }
    Shortcut { enabled: window.onScore; sequence: "Space"; onActivated: player.toggle() }
    Shortcut { enabled: window.onScore; sequence: "Left"; onActivated: player.skip(-5) }
    Shortcut { enabled: window.onScore; sequence: "Right"; onActivated: player.skip(5) }
    Shortcut { enabled: window.onScore; sequence: "Home"; onActivated: player.seek(0) }
    Shortcut { enabled: window.onScore; sequence: "F9"; onActivated: window.toggleSidebar() }
    Shortcut { enabled: window.onScore; sequences: [StandardKey.ZoomIn, "Ctrl+="]; onActivated: window.zoomBy(1.15) }
    Shortcut { enabled: window.onScore; sequences: [StandardKey.ZoomOut]; onActivated: window.zoomBy(1 / 1.15) }
    Shortcut { enabled: window.onScore; sequence: "Ctrl+0"; onActivated: scoreView.fit() }
    Shortcut { enabled: window.onScore; sequence: "Ctrl+E"; onActivated: exportMenu.open() }
    Shortcut { enabled: window.onScore; sequences: [StandardKey.Save]; onActivated: window.exportAs("musicxml", "musicxml") }
    Shortcut { enabled: window.onScore; sequence: "Ctrl+M"; onActivated: controller.openInMuseScore() }

    FileDialog {
        id: openFile
        title: window.tr.open_dialog
        fileMode: FileDialog.OpenFile
        nameFilters: [window.tr.filter_audio + " (*.mp3 *.wav *.flac *.m4a *.aac *.ogg *.opus *.wma *.aiff *.aif *.mp4 *.mkv *.mov *.webm *.mid *.midi)",
                      window.tr.filter_all + " (*)"]
        onAccepted: controller.openFile(selectedFile.toString())
    }
    FileDialog {
        id: saveFile
        property string kind
        title: window.tr.save_dialog
        fileMode: FileDialog.SaveFile
        onAccepted: controller.export(kind, selectedFile.toString())
    }

    Connections {
        target: controller
        function onMessage(text) { toast.show(text) }
    }

    Rectangle {
        id: base
        anchors.fill: parent
        radius: window.squareCorners ? 0 : Theme.radius
        color: Theme.bg
        clip: true
        border.color: window.squareCorners ? "transparent" : Theme.border

        // ── header ──────────────────────────────────────────────────────────
        Item {
            id: header
            anchors { left: parent.left; right: parent.right; top: parent.top }
            height: 52
            DragHandler { target: null; onActiveChanged: if (active) window.startSystemMove() }
            TapHandler { onDoubleTapped: window.maximized ? window.showNormal() : window.showMaximized() }

            AbstractButton {
                id: brand
                anchors { left: parent.left; leftMargin: 14; verticalCenter: parent.verticalCenter }
                implicitWidth: brandRow.implicitWidth + 12
                implicitHeight: 36
                hoverEnabled: true
                focusPolicy: Qt.NoFocus
                onClicked: if (controller.page !== "welcome" && controller.page !== "working") controller.goHome()
                background: Rectangle { radius: 10; color: brand.hovered && window.onScore ? Theme.surfaceHover : "transparent" }
                contentItem: Row {
                    id: brandRow
                    spacing: 9
                    leftPadding: 4
                    Image { anchors.verticalCenter: parent.verticalCenter; source: "icons/app.svg"; sourceSize: Qt.size(26, 26) }
                    Text {
                        anchors.verticalCenter: parent.verticalCenter
                        text: "Melograph"
                        color: Theme.text
                        font.pixelSize: 15
                        font.weight: Font.DemiBold
                    }
                }
                ToolTip.visible: hovered && window.onScore
                ToolTip.delay: 700
                ToolTip.text: window.tr.tip_home
            }

            // title and what was found, in the middle
            Row {
                anchors.centerIn: parent
                spacing: 10
                visible: window.onScore
                Text {
                    anchors.verticalCenter: parent.verticalCenter
                    text: controller.options.title || controller.fileName
                    color: Theme.text
                    font.pixelSize: 14
                    font.weight: Font.DemiBold
                    width: Math.min(implicitWidth, header.width * 0.28)
                    elide: Text.ElideRight
                }
                Repeater {
                    model: {
                        const s = controller.result.summary
                        if (!s) return []
                        return [controller.language === "de" ? s.keyDe : s.keyEn, s.meter, s.tempoUnit + " = " + s.tempo]
                    }
                    delegate: Rectangle {
                        anchors.verticalCenter: parent.verticalCenter
                        width: chip.implicitWidth + 18
                        height: 24
                        radius: 12
                        color: Theme.surface
                        border.color: Theme.border
                        Text { id: chip; anchors.centerIn: parent; text: modelData; color: Theme.textDim; font.pixelSize: 12 }
                    }
                }
            }

            Row {
                anchors { right: windowButtons.left; rightMargin: 6; verticalCenter: parent.verticalCenter }
                spacing: 4

                Row {
                    visible: window.onScore
                    spacing: 4
                    anchors.verticalCenter: parent.verticalCenter
                    Segments {
                        anchors.verticalCenter: parent.verticalCenter
                        value: controller.preferences.view
                        options: [{ icon: "score", text: window.tr.view_score, value: "score" },
                                  { icon: "roll", text: window.tr.view_roll, value: "roll" }]
                        itemPadding: 16
                        onChosen: (value) => controller.setPreference("view", value)
                    }
                    Item { width: 4; height: 1 }
                    IconButton { iconName: "minus"; iconSize: 15; tip: window.tr.tip_zoom_out; onClicked: window.zoomBy(1 / 1.15) }
                    IconButton { iconName: "plus"; iconSize: 15; tip: window.tr.tip_zoom_in; onClicked: window.zoomBy(1.15) }
                    IconButton {
                        iconName: "sliders"
                        active: controller.preferences.sidebar
                        tip: window.tr.tip_sidebar
                        onClicked: window.toggleSidebar()
                    }
                    Item { width: 4; height: 1 }
                    TextButton {
                        id: exportButton
                        anchors.verticalCenter: parent.verticalCenter
                        emphasized: true
                        iconName: "export"
                        text: window.tr.export
                        onClicked: exportMenu.opened ? exportMenu.close() : exportMenu.open()
                        ExportMenu {
                            id: exportMenu
                            objectName: "exportMenu"
                            y: exportButton.height + 8
                            x: exportButton.width - width
                            onExportRequested: (kind, extension) => window.exportAs(kind, extension)
                        }
                    }
                    Item { width: 4; height: 1 }
                }
                IconButton {
                    id: menuButton
                    iconName: "menu"
                    tip: window.tr.tip_menu
                    onClicked: appMenu.opened ? appMenu.close() : appMenu.open()
                    MenuPopup {
                        id: appMenu
                        y: menuButton.height + 8
                        x: menuButton.width - width
                    }
                }
            }

            Row {
                id: windowButtons
                anchors { right: parent.right; rightMargin: 8; verticalCenter: parent.verticalCenter }
                spacing: 2
                IconButton { iconName: "win-minimize"; iconSize: 16; tip: window.tr.tip_minimize; onClicked: window.showMinimized() }
                IconButton {
                    iconName: window.maximized ? "win-restore" : "win-maximize"
                    iconSize: 16
                    tip: window.maximized ? window.tr.tip_restore : window.tr.tip_maximize
                    onClicked: window.maximized ? window.showNormal() : window.showMaximized()
                }
                AbstractButton {
                    id: closeButton
                    implicitWidth: 34
                    implicitHeight: 34
                    hoverEnabled: true
                    focusPolicy: Qt.NoFocus
                    onClicked: window.close()
                    background: Rectangle {
                        radius: Theme.radiusSmall
                        color: closeButton.pressed ? Qt.darker(Theme.danger, 1.15) : (closeButton.hovered ? Theme.danger : "transparent")
                        Behavior on color { ColorAnimation { duration: Theme.animFast } }
                    }
                    contentItem: Item {
                        Icon { anchors.centerIn: parent; iconName: "close"; size: 18; color: closeButton.hovered ? "#ffffff" : Theme.danger }
                    }
                    ToolTip.visible: hovered
                    ToolTip.delay: 800
                    ToolTip.text: window.tr.tip_close
                }
            }
        }

        // ── pages ───────────────────────────────────────────────────────────
        Item {
            id: content
            anchors { left: parent.left; right: parent.right; top: header.bottom; bottom: parent.bottom }

            Welcome {
                anchors.fill: parent
                dragActive: window.dragActive
                opacity: controller.page === "welcome" ? 1 : 0
                visible: opacity > 0
                Behavior on opacity { NumberAnimation { duration: Theme.anim } }
                onOpenRequested: window.openDialog()
                onRecordRequested: recordDialog.open()
            }
            Working {
                anchors.fill: parent
                opacity: controller.page === "working" ? 1 : 0
                visible: opacity > 0
                Behavior on opacity { NumberAnimation { duration: Theme.anim } }
            }
            Item {
                id: scoreScreen
                anchors.fill: parent
                opacity: window.onScore ? 1 : 0
                visible: opacity > 0
                Behavior on opacity { NumberAnimation { duration: Theme.anim } }

                Item {
                    anchors { left: parent.left; right: sidebar.left; top: parent.top; bottom: transport.top }
                    ScoreView {
                        id: scoreView
                        anchors.fill: parent
                        visible: controller.preferences.view !== "roll"
                    }
                    RollView {
                        id: rollView
                        anchors.fill: parent
                        visible: controller.preferences.view === "roll"
                    }
                }
                Sidebar {
                    id: sidebar
                    anchors { right: parent.right; top: parent.top; bottom: transport.top }
                    width: controller.preferences.sidebar ? 330 : 0
                    visible: width > 0
                    clip: true
                    Behavior on width { NumberAnimation { duration: Theme.anim; easing.type: Easing.OutCubic } }
                }
                Transport {
                    id: transport
                    anchors { left: parent.left; right: parent.right; bottom: parent.bottom }
                }
            }
        }

        // ── messages ────────────────────────────────────────────────────────
        Rectangle {
            id: toast
            z: 50
            anchors { horizontalCenter: parent.horizontalCenter; bottom: parent.bottom; bottomMargin: window.onScore ? 92 : 30 }
            width: Math.min(toastText.implicitWidth + 36, window.width - 80)
            height: 38
            radius: 19
            color: Theme.dark ? "#2a262b" : "#222022"
            opacity: 0
            visible: opacity > 0
            Behavior on opacity { NumberAnimation { duration: Theme.anim } }
            function show(text) { toastText.text = text; opacity = 0.97; toastTimer.restart() }
            Text { id: toastText; anchors.centerIn: parent; width: parent.width - 36; color: "#ffffff"; font.pixelSize: 13; elide: Text.ElideMiddle; horizontalAlignment: Text.AlignHCenter }
            Timer { id: toastTimer; interval: 3800; onTriggered: toast.opacity = 0 }
        }
    }

    DropArea {
        anchors.fill: parent
        onEntered: (drag) => { window.dragActive = drag.hasUrls; if (drag.hasUrls && controller.page !== "welcome" && controller.page !== "working") controller.goHome() }
        onExited: window.dragActive = false
        onDropped: (drop) => {
            window.dragActive = false
            if (drop.hasUrls && drop.urls.length > 0) controller.openFile(drop.urls[0].toString())
        }
    }

    Preferences { id: preferences; objectName: "preferences" }
    RecordDialog { id: recordDialog; objectName: "recordDialog" }

    // the menu behind the three lines
    component MenuPopup: Popup {
        id: popup
        width: 250
        padding: 6
        focus: true
        closePolicy: Popup.CloseOnEscape | Popup.CloseOnPressOutside
        enter: Transition { NumberAnimation { property: "opacity"; from: 0; to: 1; duration: Theme.animFast } }
        exit: Transition { NumberAnimation { property: "opacity"; from: 1; to: 0; duration: Theme.animFast } }
        background: Rectangle { radius: 12; color: Theme.raised; border.color: Theme.border }
        contentItem: ColumnLayout {
            spacing: 2
            MenuEntry { iconName: "folder"; text: window.tr.menu_open; shortcut: "Ctrl+O"; onClicked: { popup.close(); window.openDialog() } }
            MenuEntry { iconName: "mic"; text: window.tr.menu_record; shortcut: "Ctrl+R"; onClicked: { popup.close(); recordDialog.open() } }
            MenuEntry { visible: window.onScore; iconName: "refresh"; text: window.tr.menu_fresh; onClicked: { popup.close(); controller.listenAgain() } }
            Rectangle { Layout.fillWidth: true; Layout.preferredHeight: 1; Layout.margins: 4; color: Theme.border }
            MenuEntry { iconName: "settings"; text: window.tr.menu_preferences; shortcut: "Ctrl+,"; onClicked: { popup.close(); preferences.open() } }
            MenuEntry { iconName: "info"; text: window.tr.menu_about; onClicked: { popup.close(); preferences.open() } }
            MenuEntry { iconName: "close"; text: window.tr.menu_quit; shortcut: "Ctrl+Q"; onClicked: window.close() }
        }
    }
    component MenuEntry: AbstractButton {
        id: entry
        property string iconName
        property string shortcut
        Layout.fillWidth: true
        implicitHeight: visible ? 36 : 0
        hoverEnabled: true
        focusPolicy: Qt.NoFocus
        background: Rectangle { radius: 8; color: entry.hovered ? Theme.surfaceHover : "transparent" }
        contentItem: RowLayout {
            spacing: 11
            Item { Layout.preferredWidth: 4 }
            Icon { iconName: entry.iconName; size: 16 }
            Text { Layout.fillWidth: true; text: entry.text; color: Theme.text; font.pixelSize: 13 }
            Text { text: entry.shortcut; color: Theme.textFaint; font.pixelSize: 11 }
            Item { Layout.preferredWidth: 4 }
        }
    }

    // resizing at the edges and corners (frameless window)
    component Grip: MouseArea {
        property int edges
        hoverEnabled: true
        visible: !window.maximized
        onPressed: window.startSystemResize(edges)
    }
    Grip { edges: Qt.LeftEdge; cursorShape: Qt.SizeHorCursor; anchors { left: parent.left; top: parent.top; bottom: parent.bottom; topMargin: 12; bottomMargin: 12 } width: 5 }
    Grip { edges: Qt.RightEdge; cursorShape: Qt.SizeHorCursor; anchors { right: parent.right; top: parent.top; bottom: parent.bottom; topMargin: 52; bottomMargin: 12 } width: 5 }
    Grip { edges: Qt.BottomEdge; cursorShape: Qt.SizeVerCursor; anchors { left: parent.left; right: parent.right; bottom: parent.bottom; leftMargin: 12; rightMargin: 12 } height: 5 }
    Grip { edges: Qt.TopEdge; cursorShape: Qt.SizeVerCursor; anchors { left: parent.left; right: parent.right; top: parent.top; leftMargin: 12; rightMargin: 52 } height: 4 }
    Grip { edges: Qt.RightEdge | Qt.BottomEdge; cursorShape: Qt.SizeFDiagCursor; anchors { right: parent.right; bottom: parent.bottom } width: 14; height: 14 }
    Grip { edges: Qt.LeftEdge | Qt.BottomEdge; cursorShape: Qt.SizeBDiagCursor; anchors { left: parent.left; bottom: parent.bottom } width: 14; height: 14 }
}
