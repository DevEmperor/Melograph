import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts

// What Melograph found, and every setting of the notation; each change writes the music again at once
Rectangle {
    id: sidebar
    readonly property var tr: controller.tr
    readonly property var o: controller.options
    readonly property var s: controller.result.summary || ({})
    readonly property bool de: controller.language === "de"
    color: Theme.panel

    function set(name, value) { controller.setOption(name, value) }
    function autoText(detail) { return tr.auto_value.replace("%1", detail) }
    function keyLabel(value) {
        const minor = value.endsWith("m")
        const root = minor ? value.slice(0, -1) : value
        if (de) {
            const names = { "C": "C", "C#": "Cis", "Db": "Des", "D": "D", "D#": "Dis", "Eb": "Es", "E": "E", "F": "F",
                            "F#": "Fis", "Gb": "Ges", "G": "G", "G#": "Gis", "Ab": "As", "A": "A", "A#": "Ais",
                            "Bb": "B", "B": "H", "Cb": "Ces" }
            const name = names[root] || root
            return minor ? name.toLowerCase() + "-Moll" : name + "-Dur"
        }
        return root.replace("b", "♭").replace("#", "♯") + (minor ? " minor" : " major")
    }
    function pitchName(midi) {
        const names = de ? ["C", "Cis", "D", "Es", "E", "F", "Fis", "G", "As", "A", "B", "H"]
                         : ["C", "C♯", "D", "E♭", "E", "F", "F♯", "G", "A♭", "A", "B♭", "B"]
        return names[midi % 12] + (Math.floor(midi / 12) - 1)
    }

    Rectangle { anchors { left: parent.left; top: parent.top; bottom: parent.bottom } width: 1; color: Theme.border }

    Flickable {
        id: flick
        anchors.fill: parent
        anchors.leftMargin: 1
        contentHeight: body.implicitHeight + 40
        boundsBehavior: Flickable.StopAtBounds
        clip: true
        ScrollBar.vertical: ScrollBar { }

        ColumnLayout {
            id: body
            x: 18
            y: 18
            width: flick.width - 36
            spacing: 14

            // ── what was found ─────────────────────────────────────────────
            GridLayout {
                Layout.fillWidth: true
                columns: 2
                columnSpacing: 8
                rowSpacing: 8
                Fact { label: sidebar.tr.key_label; value: sidebar.s.keyValue ? sidebar.keyLabel(sidebar.s.keyValue) : "–"
                       detail: sidebar.s.fifths === undefined ? "" : sidebar.s.fifths === 0 ? sidebar.tr.no_accidentals
                               : Math.abs(sidebar.s.fifths) + (sidebar.s.fifths > 0 ? " ♯" : " ♭") }
                Fact { label: sidebar.tr.meter_label; value: sidebar.s.meter || "–"; detail: sidebar.s.swing ? sidebar.tr.swing_on : "" }
                Fact { label: sidebar.tr.tempo_label; value: sidebar.s.tempo ? sidebar.s.tempoUnit + " = " + sidebar.s.tempo : "–" }
                Fact { label: sidebar.tr.bars_label; value: sidebar.s.bars || "–"; detail: sidebar.s.notes ? sidebar.s.notes + " " + sidebar.tr.notes_label : "" }
            }

            Section {
                title: sidebar.tr.section_piece
                Field {
                    Layout.fillWidth: true
                    placeholderText: sidebar.tr.title
                    text: sidebar.o.title || ""
                    onCommitted: (value) => sidebar.set("title", value)
                }
                Field {
                    Layout.fillWidth: true
                    placeholderText: sidebar.tr.composer
                    text: sidebar.o.composer || ""
                    onCommitted: (value) => sidebar.set("composer", value)
                }
            }

            Section {
                title: sidebar.tr.section_rhythm
                OptionRow {
                    label: sidebar.tr.time
                    Choice {
                        width: 142
                        current: sidebar.o.time
                        choices: [{ text: sidebar.autoText(sidebar.s.meter || "…"), value: "auto" }]
                                 .concat(controller.timeSignatures.map(t => ({ text: t, value: t })))
                        onChosen: (value) => sidebar.set("time", value)
                    }
                }
                OptionRow {
                    label: sidebar.tr.pickup
                    Choice {
                        width: 142
                        current: sidebar.o.pickup
                        choices: {
                            const per = sidebar.s.beatsPerBar || 4
                            const found = sidebar.s.pickup ? sidebar.tr.beats_n.replace("%1", sidebar.s.pickup) : sidebar.tr.pickup_none
                            const list = [{ text: sidebar.autoText(found), value: "auto" }, { text: sidebar.tr.pickup_none, value: 0 }]
                            for (let b = 1; b < per; b++) list.push({ text: sidebar.tr.beats_n.replace("%1", b), value: b })
                            return list
                        }
                        onChosen: (value) => sidebar.set("pickup", value)
                    }
                }
                OptionRow {
                    label: sidebar.tr.tempo_level
                    tip: sidebar.tr.tempo_level_tip
                    Segments {
                        value: sidebar.o.tempo
                        options: [{ text: sidebar.tr.half, value: "half" }, { text: sidebar.tr.auto, value: "auto" },
                                  { text: sidebar.tr.double, value: "double" }]
                        onChosen: (value) => sidebar.set("tempo", value)
                    }
                }
                OptionRow {
                    label: sidebar.tr.grid
                    Segments {
                        value: sidebar.o.grid
                        options: [{ text: "1/8", value: 8 }, { text: "1/16", value: 16 }, { text: "1/32", value: 32 }]
                        onChosen: (value) => sidebar.set("grid", value)
                    }
                }
                OptionRow {
                    label: sidebar.tr.triplets
                    Segments {
                        value: sidebar.o.triplets
                        options: [{ text: sidebar.tr.auto, value: "auto" }, { text: sidebar.tr.on, value: "on" }, { text: sidebar.tr.off, value: "off" }]
                        onChosen: (value) => sidebar.set("triplets", value)
                    }
                }
                OptionRow {
                    label: sidebar.tr.swing
                    Segments {
                        value: sidebar.o.swing
                        options: [{ text: sidebar.tr.auto, value: "auto" }, { text: sidebar.tr.on, value: "on" }, { text: sidebar.tr.off, value: "off" }]
                        onChosen: (value) => sidebar.set("swing", value)
                    }
                }
            }

            Section {
                title: sidebar.tr.section_key
                Choice {
                    Layout.fillWidth: true
                    current: sidebar.o.key
                    choices: [{ text: sidebar.autoText(sidebar.s.keyValue ? sidebar.keyLabel(sidebar.s.keyValue) : "…"), value: "auto" }]
                             .concat(controller.keys.map(k => ({ text: sidebar.keyLabel(k), value: k })))
                    onChosen: (value) => sidebar.set("key", value)
                }
            }

            Section {
                title: sidebar.tr.section_hands
                OptionRow {
                    label: sidebar.tr.voices
                    Segments {
                        value: sidebar.o.voices
                        options: [{ text: "1", value: 1 }, { text: "2", value: 2 }]
                        onChosen: (value) => sidebar.set("voices", value)
                    }
                }
                OptionRow {
                    label: sidebar.tr.split
                    Choice {
                        width: 142
                        current: sidebar.o.split
                        choices: {
                            const list = [{ text: sidebar.tr.split_auto, value: "auto" }]
                            for (const midi of [48, 50, 52, 53, 55, 57, 59, 60, 62, 64, 65, 67, 69, 71, 72])
                                list.push({ text: sidebar.tr.split_at.replace("%1", sidebar.pitchName(midi)), value: midi })
                            return list
                        }
                        onChosen: (value) => sidebar.set("split", value)
                    }
                }
            }

            Section {
                title: sidebar.tr.section_marks
                OptionRow {
                    label: sidebar.tr.pedal
                    Segments {
                        value: sidebar.o.pedal
                        itemPadding: 12
                        options: [{ text: sidebar.tr.pedal_lines, value: "lines" }, { text: sidebar.tr.pedal_signs, value: "signs" },
                                  { text: sidebar.tr.pedal_text, value: "text" }, { text: sidebar.tr.off, value: "off" }]
                        onChosen: (value) => sidebar.set("pedal", value)
                    }
                }
                Repeater {
                    model: ["slurs", "dynamics", "hairpins", "accents", "staccato", "graces", "ornaments", "ottava",
                            "clefs", "tempoChanges", "fermatas", "chords"]
                    delegate: OptionRow {
                        required property string modelData
                        label: sidebar.tr[modelData]
                        Toggle {
                            checked: !!sidebar.o[modelData]
                            onClicked: sidebar.set(modelData, checked)
                        }
                    }
                }
            }

            TextButton {
                Layout.fillWidth: true
                Layout.topMargin: 6
                iconName: "undo"
                text: sidebar.tr.reset
                onClicked: controller.resetOptions()
            }
        }
    }

    component Fact: Rectangle {
        property string label
        property var value
        property string detail
        Layout.fillWidth: true
        Layout.preferredHeight: 64
        radius: 12
        color: Theme.surface
        border.color: Theme.border
        Column {
            anchors { left: parent.left; right: parent.right; verticalCenter: parent.verticalCenter; margins: 12 }
            spacing: 2
            Text { text: parent.parent.label; color: Theme.textFaint; font.pixelSize: 11; font.letterSpacing: 0.4 }
            Text { width: parent.width; text: parent.parent.value; color: Theme.text; font.pixelSize: 16; font.weight: Font.DemiBold; elide: Text.ElideRight }
            Text { text: parent.parent.detail || " "; color: Theme.textDim; font.pixelSize: 11 }
        }
    }
}
