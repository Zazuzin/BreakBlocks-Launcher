# Third-Party Notices

BreakBlocks Launcher uses third-party software and connects to independent
services. This file is an attribution index; the complete licence texts shipped
with each binary package control where they differ from this summary.

## Bundled runtime components

| Component | Version used by 0.9.27 | Licence |
| --- | --- | --- |
| Python | 3.12 runtime | Python Software Foundation License Version 2 and component licences |
| Tcl/Tk | Runtime version supplied with Python | Tcl/Tk licence terms |
| CustomTkinter | 5.2.2 | MIT |
| darkdetect | 0.8.0 | BSD 3-Clause |
| Pillow | 12.3.0 | MIT-CMU / HPND-style Pillow licence and bundled component licences |
| packaging | 25.0 | Apache-2.0 or BSD-2-Clause |
| PySide6 and Qt WebEngine | 6.8.3 | LGPL-3.0-only / GPL-2.0-only / GPL-3.0-only and bundled Qt component licences |
| PyInstaller bootloader, where used | 6.16.0 | GPL-2.0-or-later with the PyInstaller bootloader exception |
| Inter | 4.1 | SIL Open Font License 1.1 |

Portable packages retain dependency licence files under the bundled runtime or
`third-party-licenses` directory. The release workflow collects those files
from the exact installed versions and stops if a required notice is missing.
The Linux package includes Inter for consistent launcher typography across
Ubuntu and Steam Deck systems.

## Downloaded rather than bundled

Minecraft, Java, Fabric, Quilt, Forge, NeoForge, mods, and launcher updates are
not relicensed by BreakBlocks Launcher. They are downloaded from their
respective providers only when requested and remain subject to those providers'
licences and terms. Installing a project through the launcher does not transfer
ownership or grant rights beyond the project's own licence.

## Artwork and names

Minecraft, Mojang, Microsoft, Modrinth, GitHub, Patreon, YouTube, Discord, and
other third-party names and marks belong to their respective owners. Their use
does not indicate endorsement.

The built-in block-style instance icons are original launcher artwork generated
by `tools/generate_block_icons.py`; they are not files extracted from Minecraft.
Other BreakBlocks and community artwork remains subject to the rights of its
respective creator or owner.

## Project source licence

The original source code for BreakBlocks Launcher is licensed under the GNU
General Public License version 3 only (`GPL-3.0-only`). See `LICENSE` for the
complete terms. Third-party components keep their own licences, and BreakBlocks
branding, community artwork, and third-party marks are not relicensed by that
source-code licence unless their owners explicitly say otherwise.
