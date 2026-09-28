#!/usr/bin/env python3
"""Embed a multi-resolution ICO as the application icon in a PE executable."""

import argparse
import pathlib
import shutil
import struct
import subprocess
import tempfile

RESOURCE_DIRECTORY = 2
RESOURCE_ICON = 3
RESOURCE_GROUP_ICON = 14
LANGUAGE_ENGLISH_US = 1033


def align(value, boundary):
    return (value + boundary - 1) // boundary * boundary


def read_pe_layout(path):
    data = pathlib.Path(path).read_bytes()
    pe_offset = struct.unpack_from("<I", data, 0x3C)[0]
    if data[pe_offset : pe_offset + 4] != b"PE\0\0":
        raise ValueError("Input is not a PE executable")
    coff_offset = pe_offset + 4
    section_count = struct.unpack_from("<H", data, coff_offset + 2)[0]
    optional_size = struct.unpack_from("<H", data, coff_offset + 16)[0]
    optional_offset = coff_offset + 20
    magic = struct.unpack_from("<H", data, optional_offset)[0]
    if magic != 0x20B:
        raise ValueError("Only 64-bit PE32+ executables are supported")
    section_alignment = struct.unpack_from("<I", data, optional_offset + 32)[0]
    image_base = struct.unpack_from("<Q", data, optional_offset + 24)[0]
    section_table = optional_offset + optional_size
    highest_end = 0
    for index in range(section_count):
        offset = section_table + index * 40
        virtual_size, virtual_address, raw_size = struct.unpack_from("<III", data, offset + 8)
        highest_end = max(highest_end, virtual_address + max(virtual_size, raw_size))
    return {
        "resource_rva": align(highest_end, section_alignment),
        "image_base": image_base,
        "section_alignment": section_alignment,
        "optional_offset": optional_offset,
        "section_table": section_table,
        "section_count": section_count,
    }


def read_ico(path):
    data = pathlib.Path(path).read_bytes()
    reserved, icon_type, count = struct.unpack_from("<HHH", data, 0)
    if reserved != 0 or icon_type != 1 or count < 1:
        raise ValueError("Input is not a Windows icon file")
    images = []
    for index in range(count):
        entry = struct.unpack_from("<BBBBHHII", data, 6 + index * 16)
        width, height, colours, reserved_byte, planes, bit_count, size, offset = entry
        payload = data[offset : offset + size]
        if len(payload) != size:
            raise ValueError("ICO image data is truncated")
        images.append(
            {
                "width": width,
                "height": height,
                "colours": colours,
                "reserved": reserved_byte,
                "planes": planes,
                "bit_count": bit_count,
                "payload": payload,
            }
        )
    return images


def resource_directory(id_entries):
    return struct.pack("<IIHHHH", 0, 0, 0, 0, 0, id_entries)


def build_resource(icon_path, resource_rva):
    icons = read_ico(icon_path)
    count = len(icons)
    root_offset = 0
    icon_type_offset = 16 + 2 * 8
    group_type_offset = icon_type_offset + 16 + count * 8
    icon_languages_offset = group_type_offset + 16 + 8
    group_language_offset = icon_languages_offset + count * 24
    icon_data_entries_offset = group_language_offset + 24
    group_data_entry_offset = icon_data_entries_offset + count * 16
    data_offset = align(group_data_entry_offset + 16, 4)

    blob = bytearray(data_offset)
    blob[root_offset : root_offset + 16] = resource_directory(2)
    struct.pack_into("<II", blob, root_offset + 16, RESOURCE_ICON, 0x80000000 | icon_type_offset)
    struct.pack_into(
        "<II", blob, root_offset + 24, RESOURCE_GROUP_ICON, 0x80000000 | group_type_offset
    )

    blob[icon_type_offset : icon_type_offset + 16] = resource_directory(count)
    for index in range(count):
        language_offset = icon_languages_offset + index * 24
        struct.pack_into(
            "<II", blob, icon_type_offset + 16 + index * 8, index + 1, 0x80000000 | language_offset
        )
        blob[language_offset : language_offset + 16] = resource_directory(1)
        struct.pack_into(
            "<II",
            blob,
            language_offset + 16,
            LANGUAGE_ENGLISH_US,
            icon_data_entries_offset + index * 16,
        )

    blob[group_type_offset : group_type_offset + 16] = resource_directory(1)
    struct.pack_into("<II", blob, group_type_offset + 16, 1, 0x80000000 | group_language_offset)
    blob[group_language_offset : group_language_offset + 16] = resource_directory(1)
    struct.pack_into(
        "<II", blob, group_language_offset + 16, LANGUAGE_ENGLISH_US, group_data_entry_offset
    )

    icon_offsets = []
    for icon in icons:
        icon_offsets.append(len(blob))
        blob.extend(icon["payload"])
        while len(blob) % 4:
            blob.append(0)

    group_offset = len(blob)
    group = bytearray(struct.pack("<HHH", 0, 1, count))
    for index, icon in enumerate(icons):
        group.extend(
            struct.pack(
                "<BBBBHHIH",
                icon["width"],
                icon["height"],
                icon["colours"],
                icon["reserved"],
                icon["planes"],
                icon["bit_count"],
                len(icon["payload"]),
                index + 1,
            )
        )
    blob.extend(group)
    while len(blob) % 4:
        blob.append(0)

    for index, icon in enumerate(icons):
        struct.pack_into(
            "<IIII",
            blob,
            icon_data_entries_offset + index * 16,
            resource_rva + icon_offsets[index],
            len(icon["payload"]),
            0,
            0,
        )
    struct.pack_into(
        "<IIII", blob, group_data_entry_offset, resource_rva + group_offset, len(group), 0, 0
    )
    return bytes(blob)


def patch_resource_directory(path, expected_rva, resource_size):
    data = bytearray(pathlib.Path(path).read_bytes())
    layout = read_pe_layout(path)
    resource_section = None
    for index in range(layout["section_count"]):
        offset = layout["section_table"] + index * 40
        name = bytes(data[offset : offset + 8]).rstrip(b"\0")
        if name == b".rsrc":
            virtual_size, virtual_address = struct.unpack_from("<II", data, offset + 8)
            resource_section = (virtual_address, virtual_size)
            break
    if resource_section is None:
        raise RuntimeError("objcopy did not create the .rsrc section")
    if resource_section[0] != expected_rva:
        raise RuntimeError(f"Unexpected .rsrc RVA: 0x{resource_section[0]:x}")
    data_directory = layout["optional_offset"] + 112
    struct.pack_into(
        "<II", data, data_directory + RESOURCE_DIRECTORY * 8, expected_rva, resource_size
    )
    checksum_offset = layout["optional_offset"] + 64
    struct.pack_into("<I", data, checksum_offset, 0)
    checksum = pe_checksum(data)
    struct.pack_into("<I", data, checksum_offset, checksum)
    pathlib.Path(path).write_bytes(data)


def pe_checksum(data):
    total = 0
    length = len(data)
    padded = bytes(data) + (b"\0" if length % 2 else b"")
    for offset in range(0, len(padded), 2):
        total += padded[offset] | (padded[offset + 1] << 8)
        total = (total & 0xFFFF) + (total >> 16)
    total = (total & 0xFFFF) + (total >> 16)
    return (total + length) & 0xFFFFFFFF


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("input_exe", type=pathlib.Path)
    parser.add_argument("icon", type=pathlib.Path)
    parser.add_argument("output_exe", type=pathlib.Path)
    arguments = parser.parse_args()
    objcopy = shutil.which("objcopy")
    if not objcopy:
        raise RuntimeError("GNU objcopy is required")
    layout = read_pe_layout(arguments.input_exe)
    resource = build_resource(arguments.icon, layout["resource_rva"])
    arguments.output_exe.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="breakblocks-icon-") as temporary:
        resource_path = pathlib.Path(temporary) / "breakblocks.rsrc"
        resource_path.write_bytes(resource)
        subprocess.run(
            [
                objcopy,
                "--add-section",
                f".rsrc={resource_path}",
                "--set-section-flags",
                ".rsrc=alloc,load,data,readonly",
                "--change-section-vma",
                f".rsrc=0x{layout['image_base'] + layout['resource_rva']:x}",
                str(arguments.input_exe),
                str(arguments.output_exe),
            ],
            check=True,
        )
    patch_resource_directory(arguments.output_exe, layout["resource_rva"], len(resource))


if __name__ == "__main__":
    main()
