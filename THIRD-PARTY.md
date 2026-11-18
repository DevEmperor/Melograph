# Third-party software

Melograph itself is licensed under the GNU General Public License, version 3 or later
(see [LICENSE](LICENSE)). It stands on the work of others. The AppImage contains the
following components unchanged, each under its own licence. The full licence text of
every Python package is included in the AppImage, in
`usr/python/lib/python3.14/site-packages/<package>.dist-info/`.

## Recognition

| Component | Purpose | Licence |
|---|---|---|
| [Transkun](https://github.com/Yujia-Yan/Transkun) 2.0 (Yujia Yan, Zhiyao Duan), with its pretrained model | Notes and pedal from the audio | MIT |
| [Beat This!](https://github.com/CPJKU/beat_this) (Francesco Foscarin, Jan Schlüter, Gerhard Widmer), model `final0` | Beats and downbeats | MIT |
| [PyTorch](https://pytorch.org) and torchaudio, CPU build | Runs both models | BSD-3-Clause, BSD-2-Clause |
| [NumPy](https://numpy.org), [SciPy](https://scipy.org) | Signal processing | BSD-3-Clause |
| [python-soxr](https://github.com/dofuuz/python-soxr) with libsoxr | Resampling for Beat This! | LGPL-2.1-or-later |

## Notation and engraving

| Component | Purpose | Licence |
|---|---|---|
| [music21](https://github.com/cuthbertLab/music21) | Writing MusicXML | BSD-3-Clause |
| [Verovio](https://www.verovio.org) | Score preview and PDF | LGPL-3.0-or-later |
| [Leland](https://github.com/MuseScoreFonts/Leland) and Leipzig music fonts, inside Verovio | Music symbols | SIL Open Font License 1.1 |
| [pretty_midi](https://github.com/craffel/pretty-midi), [mido](https://github.com/mido/mido) | MIDI files | MIT |

## Window, sound and files

| Component | Purpose | Licence |
|---|---|---|
| [Qt 6](https://www.qt.io) through [PySide6](https://doc.qt.io/qtforpython-6/) | The window | LGPL-3.0 |
| [PyAV](https://github.com/PyAV-Org/PyAV) 19.0 with the [FFmpeg](https://ffmpeg.org) 9.0 libraries | Opening any audio or video file | BSD-3-Clause; FFmpeg as built for PyAV (with x264 and x265): GPL-3.0-or-later |
| [miniaudio](https://miniaud.io) through [pyminiaudio](https://github.com/irmen/pyminiaudio) | Playback and recording | MIT-0 / public domain, MIT |
| [Rich](https://github.com/Textualize/rich) | The command line | MIT |
| [CPython](https://www.python.org) 3.14, built by [python-build-standalone](https://github.com/astral-sh/python-build-standalone) | Runs Melograph | PSF-2.0 (and the licences of its parts) |

## Source code of the GPL and LGPL components

All of them are used as shared libraries, exactly as their projects publish them,
without changes:

- Qt 6.12 and PySide6 6.12: [code.qt.io](https://code.qt.io), [download.qt.io](https://download.qt.io/official_releases/QtForPython/)
- Verovio 6.4.1: [github.com/rism-digital/verovio](https://github.com/rism-digital/verovio)
- libsoxr in python-soxr 1.1.0: [github.com/dofuuz/python-soxr](https://github.com/dofuuz/python-soxr)
- FFmpeg 9.0.2 and its codec libraries in PyAV 19.0.2, with the scripts that build them:
  [ffmpeg.org/download.html](https://ffmpeg.org/download.html), [github.com/PyAV-Org/pyav-ffmpeg](https://github.com/PyAV-Org/pyav-ffmpeg)

To use your own builds of them, extract the AppImage (`./Melograph-*.AppImage
--appimage-extract`), replace the libraries under `squashfs-root/usr/python/lib/python3.14/site-packages/`
and start `squashfs-root/AppRun`. How the AppImage is put together is in
[packaging/appimage/build.sh](packaging/appimage/build.sh).
