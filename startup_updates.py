"""Read-only update checks across installed Minecraft instances."""

from pathlib import Path

import modrinth_client


def check_mods(root, instances, is_busy=lambda _instance: False):
    instances_root = (Path(root) / "instances").resolve()
    available = []
    failures = []
    for instance in instances:
        if (
            not instance.get("installed")
            or instance.get("loader") not in modrinth_client.SUPPORTED_LOADERS
            or is_busy(instance)
        ):
            continue
        folder = instances_root / str(instance.get("id", ""))
        if folder.is_symlink() or folder.resolve().parent != instances_root:
            continue
        mods = folder / "minecraft" / "mods"
        if (
            (folder / "minecraft").is_symlink()
            or mods.is_symlink()
            or not mods.is_dir()
            or not any(mods.glob("*.jar*"))
        ):
            continue
        try:
            manager = modrinth_client.ModManager(folder, instance["version"], instance["loader"])
            updates = manager.check_updates(read_only=True)
            if updates:
                available.append(
                    {
                        "instance_id": instance["id"],
                        "instance_name": instance["name"],
                        "updates": updates,
                    }
                )
        except Exception as error:
            failures.append((instance["id"], str(error)))
    return available, failures
