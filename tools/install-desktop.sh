#!/usr/bin/env bash
# Adds Melograph from this folder to the application menu of the current user
# (and a `melograph` command in ~/.local/bin). Remove with: tools/install-desktop.sh --remove
# The switch "In the application menu" in Melograph's preferences does the same for the menu.
set -euo pipefail

here="$(cd "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")/.." && pwd)"
apps="${XDG_DATA_HOME:-$HOME/.local/share}/applications"
icons="${XDG_DATA_HOME:-$HOME/.local/share}/icons/hicolor/scalable/apps"
bin="$HOME/.local/bin"
id="net.devemperor.Melograph"

if [[ "${1:-}" == "--remove" ]]; then
    rm -f "$apps/$id.desktop" "$icons/$id.svg" "$bin/melograph"
    echo "Melograph removed from the menu."
    exit 0
fi

mkdir -p "$apps" "$icons" "$bin"
install -m 644 "$here/melograph/gui/icons/$id.svg" "$icons/$id.svg"
sed "s|^Exec=melograph|Exec=\"$here/melograph.sh\"|" "$here/melograph/gui/$id.desktop" > "$apps/$id.desktop"
ln -sf "$here/melograph.sh" "$bin/melograph"
update-desktop-database "$apps" >/dev/null 2>&1 || true
echo "Melograph is in the menu now, and \`melograph\` works in any terminal (if ~/.local/bin is on PATH)."
