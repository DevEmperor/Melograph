import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts

// The ways out: MusicXML for MuseScore, PDF, MIDI as written or as played, MEI – or straight into MuseScore
Popup {
    id: menu
    signal exportRequested(string kind, string extension)
    readonly property var tr: controller.tr
    width: 290
    padding: 6
    modal: false
    focus: true
    closePolicy: Popup.CloseOnEscape | Popup.CloseOnPressOutside
    enter: Transition {
        NumberAnimation { property: "opacity"; from: 0; to: 1; duration: Theme.animFast }
        NumberAnimation { property: "y"; from: menu.y - 6; to: menu.y; duration: Theme.anim; easing.type: Easing.OutCubic }
    }
    exit: Transition { NumberAnimation { property: "opacity"; from: 1; to: 0; duration: Theme.animFast } }
    background: Rectangle { radius: 12; color: Theme.raised; border.color: Theme.border }

    contentItem: ColumnLayout {
        spacing: 2
        Entry { iconName: "score"; text: menu.tr.export_musicxml; detail: ".musicxml"; onClicked: menu.pick("musicxml", "musicxml") }
        Entry { iconName: "print"; text: menu.tr.export_pdf; detail: ".pdf"; onClicked: menu.pick("pdf", "pdf") }
        Entry { iconName: "note"; text: menu.tr.export_midi_score; detail: ".mid"; onClicked: menu.pick("midi-score", "mid") }
        Entry { iconName: "wave"; text: menu.tr.export_midi_performance; detail: ".mid"; onClicked: menu.pick("midi-performance", "mid") }
        Entry { iconName: "file"; text: menu.tr.export_mei; detail: ".mei"; onClicked: menu.pick("mei", "mei") }
        Rectangle { Layout.fillWidth: true; Layout.preferredHeight: 1; Layout.margins: 4; color: Theme.border }
        Entry {
            iconName: "external"
            text: menu.tr.open_musescore
            enabled: controller.museScore.length > 0
            accent: true
            onClicked: { menu.close(); controller.openInMuseScore() }
        }
    }

    function pick(kind, extension) {
        menu.close()
        menu.exportRequested(kind, extension)
    }

    component Entry: AbstractButton {
        id: entry
        property string iconName
        property string detail
        property bool accent: false
        Layout.fillWidth: true
        implicitHeight: 38
        hoverEnabled: true
        focusPolicy: Qt.NoFocus
        opacity: enabled ? 1 : 0.4
        background: Rectangle { radius: 8; color: entry.hovered ? Theme.surfaceHover : "transparent" }
        contentItem: RowLayout {
            spacing: 11
            Item { Layout.preferredWidth: 4 }
            Icon { iconName: entry.iconName; size: 17; color: entry.accent ? Theme.accent : Theme.textDim }
            Text { Layout.fillWidth: true; text: entry.text; color: Theme.text; font.pixelSize: 13; elide: Text.ElideRight }
            Text { text: entry.detail; color: Theme.textFaint; font.pixelSize: 11 }
            Item { Layout.preferredWidth: 4 }
        }
    }
}
