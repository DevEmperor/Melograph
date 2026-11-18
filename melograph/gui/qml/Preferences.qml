import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts

// Preferences and what Melograph is
Popup {
    id: dialog
    readonly property var tr: controller.tr
    readonly property var p: controller.preferences
    property string cacheText: ""
    anchors.centerIn: Overlay.overlay
    width: Math.min(560, parent ? parent.width - 60 : 560)
    height: Math.min(implicitHeight, parent ? parent.height - 60 : 700)
    padding: 0
    modal: true
    focus: true
    onOpened: cacheText = controller.cacheSize()
    Overlay.modal: Rectangle { color: Theme.dark ? "#99000000" : "#55000000" }
    enter: Transition {
        NumberAnimation { property: "opacity"; from: 0; to: 1; duration: Theme.anim }
        NumberAnimation { property: "scale"; from: 0.97; to: 1; duration: Theme.anim; easing.type: Easing.OutCubic }
    }
    exit: Transition { NumberAnimation { property: "opacity"; from: 1; to: 0; duration: Theme.animFast } }
    background: Rectangle { radius: 16; color: Theme.raised; border.color: Theme.border }

    contentItem: Flickable {
        implicitHeight: body.implicitHeight + 48
        contentHeight: body.implicitHeight + 48
        boundsBehavior: Flickable.StopAtBounds
        clip: true
        ScrollBar.vertical: ScrollBar { }

        ColumnLayout {
            id: body
            x: 24
            y: 22
            width: dialog.width - 48
            spacing: 16

            RowLayout {
                Layout.fillWidth: true
                Text { Layout.fillWidth: true; text: dialog.tr.preferences; color: Theme.text; font.pixelSize: 18; font.weight: Font.DemiBold }
                IconButton { iconName: "close"; tip: dialog.tr.close; onClicked: dialog.close() }
            }

            OptionRow {
                label: dialog.tr.language
                Segments {
                    value: dialog.p.language
                    options: [{ text: dialog.tr.lang_auto, value: "auto" }, { text: "Deutsch", value: "de" }, { text: "English", value: "en" }]
                    onChosen: (value) => controller.setPreference("language", value)
                }
            }
            ColumnLayout {
                Layout.fillWidth: true
                spacing: 4
                OptionRow {
                    label: dialog.tr.device
                    Segments {
                        value: dialog.p.device
                        options: [{ text: dialog.tr.device_auto, value: "auto" }, { text: dialog.tr.device_cpu, value: "cpu" },
                                  { text: dialog.tr.device_gpu, value: "cuda", enabled: controller.gpuAvailable }]
                        onChosen: (value) => controller.setPreference("device", value)
                    }
                }
                Note { visible: !controller.gpuAvailable; text: dialog.tr.gpu_missing }
            }
            ColumnLayout {
                Layout.fillWidth: true
                visible: controller.canAddToMenu
                spacing: 4
                OptionRow {
                    label: dialog.tr.in_menu
                    Toggle { checked: controller.inMenu; onClicked: controller.setInMenu(checked) }
                }
                Note { text: dialog.tr.in_menu_note }
            }

            Divider { }
            Info { title: dialog.tr.sound; text: controller.soundInfo }
            Info { title: dialog.tr.musescore; text: controller.museScore ? dialog.tr.musescore_found : dialog.tr.musescore_missing }
            OptionRow {
                visible: controller.museScore.length > 0
                label: dialog.tr.export_open
                Toggle { checked: !!dialog.p.openAfterExport; onClicked: controller.setPreference("openAfterExport", checked) }
            }
            RowLayout {
                Layout.fillWidth: true
                spacing: 12
                Info { Layout.fillWidth: true; title: dialog.tr.cache; text: dialog.tr.cache_text.replace("%1", dialog.cacheText) }
                TextButton {
                    text: dialog.tr.cache_clear
                    iconName: "trash"
                    onClicked: { controller.clearCache(); dialog.cacheText = controller.cacheSize() }
                }
            }

            Divider { }
            RowLayout {
                Layout.fillWidth: true
                spacing: 14
                Image { source: "icons/app.svg"; sourceSize: Qt.size(48, 48) }
                ColumnLayout {
                    spacing: 2
                    Text { text: "Melograph"; color: Theme.text; font.pixelSize: 16; font.weight: Font.DemiBold }
                    Text { text: dialog.tr.version.replace("%1", controller.version) + "  ·  " + dialog.tr.tagline; color: Theme.textFaint; font.pixelSize: 12 }
                }
            }
            Text {
                Layout.fillWidth: true
                text: dialog.tr.about_text
                color: Theme.textDim
                font.pixelSize: 12
                wrapMode: Text.WordWrap
                lineHeight: 1.25
            }
        }
    }

    component Divider: Rectangle { Layout.fillWidth: true; Layout.preferredHeight: 1; color: Theme.border }
    component Note: Text { Layout.fillWidth: true; color: Theme.textFaint; font.pixelSize: 12; wrapMode: Text.WordWrap }
    component Info: ColumnLayout {
        property string title
        property string text
        Layout.fillWidth: true
        spacing: 3
        Text { text: parent.title; color: Theme.textDim; font.pixelSize: 12 }
        Text { Layout.fillWidth: true; text: parent.text; color: Theme.textFaint; font.pixelSize: 12; wrapMode: Text.WordWrap }
    }
}
