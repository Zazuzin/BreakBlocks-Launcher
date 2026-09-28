#!/usr/bin/env python3
"""Generate BreakBlocks Launcher's original block-style instance icons.

These are purpose-built launcher assets, not files extracted from Minecraft.
"""

import random
from pathlib import Path

from PIL import Image, ImageDraw

OUTPUT = Path(__file__).resolve().parents[1] / "assets" / "instance_icons"

PALETTES = {
    "grass_block": ((117, 79, 49), (82, 55, 38), (96, 166, 63), (142, 194, 81)),
    "stone": ((121, 124, 126), (91, 94, 98), (154, 156, 156), (108, 111, 114)),
    "dirt": ((123, 82, 52), (82, 54, 39), (157, 108, 66), (103, 68, 47)),
    "cobblestone": ((111, 115, 116), (70, 73, 75), (148, 151, 151), (91, 95, 96)),
    "oak_planks": ((174, 132, 76), (112, 78, 43), (205, 164, 99), (147, 105, 57)),
    "bricks": ((153, 72, 58), (91, 45, 43), (191, 96, 75), (188, 168, 142)),
    "glass": ((125, 193, 204), (72, 129, 146), (211, 244, 245), (154, 218, 225)),
    "obsidian": ((39, 25, 60), (20, 13, 34), (79, 48, 111), (53, 31, 82)),
    "netherrack": ((119, 49, 48), (72, 31, 37), (163, 70, 62), (99, 39, 45)),
    "end_stone": ((218, 220, 151), (155, 157, 100), (237, 236, 177), (186, 188, 123)),
    "diamond_ore": ((111, 115, 116), (79, 82, 84), (151, 154, 154), (55, 224, 213)),
    "emerald_ore": ((111, 115, 116), (79, 82, 84), (151, 154, 154), (48, 205, 109)),
    "gold_ore": ((111, 115, 116), (79, 82, 84), (151, 154, 154), (246, 205, 61)),
    "iron_ore": ((111, 115, 116), (79, 82, 84), (151, 154, 154), (216, 174, 137)),
    "redstone_ore": ((111, 115, 116), (79, 82, 84), (151, 154, 154), (226, 49, 45)),
    "amethyst_block": ((125, 78, 170), (72, 43, 108), (187, 128, 221), (221, 174, 239)),
    "copper_block": ((181, 99, 62), (113, 59, 43), (220, 132, 82), (72, 154, 131)),
    "deepslate": ((70, 72, 75), (39, 42, 45), (99, 102, 104), (55, 59, 62)),
    "moss_block": ((80, 118, 48), (46, 76, 34), (117, 151, 68), (66, 99, 40)),
    "sand": ((218, 202, 151), (177, 158, 112), (239, 225, 176), (201, 184, 135)),
    "snow_block": ((226, 242, 246), (169, 207, 219), (247, 252, 252), (201, 226, 232)),
    "pumpkin": ((202, 104, 30), (116, 58, 22), (235, 140, 47), (81, 111, 35)),
    "melon": ((112, 155, 50), (52, 92, 34), (151, 190, 70), (31, 68, 32)),
    "crafting_table": ((143, 91, 48), (79, 48, 31), (190, 137, 74), (207, 175, 105)),
    "bookshelf": ((146, 95, 52), (78, 50, 31), (191, 138, 78), (196, 62, 67)),
}


def speckle(draw, rng, colors, count=45):
    for _ in range(count):
        x, y = rng.randrange(16), rng.randrange(16)
        draw.point((x, y), fill=rng.choice(colors))


def make_icon(name, palette):
    base, dark, light, accent = palette
    rng = random.Random(name)
    image = Image.new("RGBA", (16, 16), (*base, 255))
    draw = ImageDraw.Draw(image)
    speckle(draw, rng, [dark, light, base], 48)

    if name == "grass_block":
        draw.rectangle((0, 0, 15, 4), fill=accent)
        draw.rectangle((0, 4, 15, 5), fill=(72, 128, 49))
        for x in (1, 5, 8, 12, 14):
            draw.line((x, 4, x, 6 + rng.randrange(3)), fill=(75, 128, 46))
    elif name == "cobblestone":
        for y in (0, 5, 10, 15):
            draw.line((0, y, 15, y), fill=dark)
        for row, y in enumerate((0, 5, 10)):
            offset = 2 if row % 2 else 0
            for x in range(offset, 16, 5):
                draw.line((x, y, x, min(15, y + 5)), fill=dark)
    elif name == "oak_planks":
        for y in (4, 9, 14):
            draw.line((0, y, 15, y), fill=dark)
        draw.line((8, 0, 8, 4), fill=dark)
        draw.line((4, 5, 4, 9), fill=dark)
        draw.line((11, 10, 11, 14), fill=dark)
    elif name == "bricks":
        image.paste((*accent, 255), (0, 0, 16, 16))
        draw = ImageDraw.Draw(image)
        for y in (4, 9, 14):
            draw.line((0, y, 15, y), fill=dark)
        for row, y in enumerate((0, 5, 10)):
            for x in range(3 if row % 2 else 7, 16, 8):
                draw.line((x, y, x, min(y + 4, 15)), fill=dark)
    elif name == "glass":
        image = Image.new("RGBA", (16, 16), (*base, 170))
        draw = ImageDraw.Draw(image)
        draw.rectangle((0, 0, 15, 15), outline=dark)
        draw.line((2, 2, 7, 2), fill=light, width=2)
        draw.line((2, 2, 2, 7), fill=light, width=2)
        draw.line((10, 13, 13, 10), fill=accent)
    elif name in {"diamond_ore", "emerald_ore", "gold_ore", "iron_ore", "redstone_ore"}:
        for x, y in ((3, 3), (11, 4), (7, 9), (13, 12), (3, 13)):
            draw.rectangle((x, y, x + 1, y + 1), fill=accent)
            if x < 12:
                draw.point((x + 2, y), fill=accent)
    elif name == "copper_block":
        for value in (5, 10):
            draw.line((0, value, 15, value), fill=dark)
            draw.line((value, 0, value, 15), fill=dark)
        for x, y in ((2, 3), (12, 2), (7, 8), (3, 12), (12, 13)):
            draw.rectangle((x, y, x + 1, y + 1), fill=accent)
    elif name == "deepslate":
        for offset in range(-8, 17, 5):
            draw.line((offset, 15, offset + 9, 0), fill=light)
    elif name == "pumpkin":
        for x in (3, 7, 11):
            draw.line((x, 0, x, 15), fill=dark)
        draw.rectangle((7, 0, 8, 2), fill=accent)
    elif name == "melon":
        for x in (2, 6, 10, 14):
            draw.line((x, 0, x, 15), fill=dark)
    elif name == "crafting_table":
        draw.rectangle((1, 1, 14, 14), outline=dark, width=2)
        draw.line((5, 1, 5, 14), fill=light)
        draw.line((10, 1, 10, 14), fill=light)
        draw.line((1, 7, 14, 7), fill=dark)
    elif name == "bookshelf":
        draw.rectangle((0, 0, 15, 2), fill=dark)
        draw.rectangle((0, 7, 15, 9), fill=dark)
        draw.rectangle((0, 14, 15, 15), fill=dark)
        book_colors = ((181, 47, 51), (50, 101, 167), (199, 159, 51), (71, 135, 76))
        x = 1
        for row_y in (3, 10):
            for width in (2, 3, 2, 3, 2):
                color = rng.choice(book_colors)
                draw.rectangle((x, row_y, min(14, x + width - 1), row_y + 3), fill=color)
                x += width
            x = 1
    elif name == "amethyst_block":
        for x, y in ((2, 2), (9, 1), (5, 7), (12, 8), (3, 12), (9, 13)):
            draw.polygon(((x, y - 1), (x + 1, y), (x, y + 2), (x - 1, y)), fill=accent)

    return image.resize((64, 64), Image.Resampling.NEAREST)


def main():
    OUTPUT.mkdir(parents=True, exist_ok=True)
    for name, palette in PALETTES.items():
        make_icon(name, palette).save(OUTPUT / f"{name}.png", "PNG", optimize=True)
    print(f"Generated {len(PALETTES)} block icons in {OUTPUT}")


if __name__ == "__main__":
    main()
