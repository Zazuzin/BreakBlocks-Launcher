"""Conservative explanations of common Minecraft startup failures."""

import re
from pathlib import Path


def _result(title, explanation, next_step, action=None):
    return {"title": title, "explanation": explanation, "next_step": next_step, "action": action}


def diagnose_text(text):
    """Recognize evidence in the actual error; do not infer a cause from exit codes."""
    text = str(text)
    lowered = text.lower()
    if "no such file or directory" in lowered and re.search(
        r"[/\\]java(?:\.exe)?['\"]?$", text.strip(), re.I
    ):
        return _result(
            "The selected Java runtime is missing",
            "The Java executable saved in this instance's launch profile could not be found.",
            "Set Java to Auto in Settings, then use Repair installation to select or download its runtime.",
            "repair",
        )
    if "instance-launch.json" in lowered and "no such file or directory" in lowered:
        return _result(
            "The instance launch profile is missing",
            "Minecraft's installed launch profile could not be found.",
            "Use Repair installation in Instance Tools to rebuild the launch profile.",
            "repair",
        )
    if "unsupportedclassversionerror" in lowered or "compiled by a more recent version" in lowered:
        versions = re.findall(r"class file version (\d+)(?:\.\d+)?", text, re.I)
        required = int(versions[0]) - 44 if versions and int(versions[0]) >= 49 else None
        detail = f" This component requires Java {required} or newer." if required else ""
        return _result(
            "Java version is too old",
            "Minecraft or one of its mods was compiled for a newer Java version." + detail,
            "Set Java to Auto in Settings, then use Repair installation in Instance Tools. "
            "If the error names a mod, also check its Minecraft and Java requirements.",
            "repair",
        )
    if any(
        value in lowered for value in ("requires java", "java version mismatch", "unsupported java")
    ):
        return _result(
            "Java version does not match",
            "The launch error reports an unsupported Java version.",
            "Set Java to Auto in Settings and repair the instance to select its required runtime.",
            "repair",
        )
    if any(
        value in lowered
        for value in (
            "incompatible mods found",
            "mod resolution encountered an incompatible mod set",
            "modresolutionexception",
            "incompatible mod set",
        )
    ):
        lines = [
            line.strip()
            for line in text.splitlines()
            if re.search(r"requires|depends|missing mandatory", line, re.I)
        ]
        detail = re.sub(r"^\[[^\]]*\]\s*", "", lines[0])[:200] if lines else ""
        return _result(
            "Mods or dependencies do not match",
            "The loader rejected the installed mod combination."
            + ("\n" + detail if detail else ""),
            "Open Modrinth and check the named mods and their dependencies for this Minecraft "
            "version and loader. If this began after an update, restore the backup made before it.",
            "mods",
        )
    if any(
        value in lowered
        for value in (
            "missing mandatory dependencies",
            "requires fabric-api",
            "requires version",
            "depends on",
        )
    ) and any(value in lowered for value in ("mod ", "fabric", "forge", "dependency")):
        return _result(
            "A mod dependency is missing or incompatible",
            "The error names another mod or library required by an installed mod.",
            "Use View report to find the dependency and install a compatible build through Modrinth. "
            "You can also restore the backup from before the mod change.",
            "mods",
        )
    if any(
        value in lowered
        for value in (
            "outofmemoryerror",
            "could not reserve enough space",
            "invalid maximum heap size",
        )
    ):
        return _result(
            "Minecraft could not allocate memory",
            "Java reported a memory allocation failure.",
            "Check RAM Allocation in Edit Instance. Increase it for a Java heap error, or lower it "
            "if Java cannot reserve the requested memory. Leave RAM available for your operating system.",
            "edit",
        )
    if any(
        value in lowered
        for value in ("glfw error 65542", "does not support opengl", "failed to create window")
    ):
        return _result(
            "Graphics initialization failed",
            "Minecraft could not create its graphics window.",
            "Install the graphics driver supplied by your GPU or device manufacturer, then restart. "
            "If this started after adding a graphics mod, restore the earlier mod backup.",
        )
    if any(
        value in lowered
        for value in (
            "could not find or load main class",
            "classnotfoundexception: net.minecraft",
            "invalid or corrupt jarfile",
        )
    ):
        return _result(
            "Minecraft installation files are missing or damaged",
            "Java could not load a required Minecraft launch file.",
            "Use Repair installation in Instance Tools to download and rebuild the launch files.",
            "repair",
        )
    if "mixin" in lowered and any(
        value in lowered
        for value in ("apply failed", "mixinapplyerror", "injectionerror", "invalidmixinexception")
    ):
        return _result(
            "A mod failed while loading",
            "The report contains a mixin loading error. A mod mismatch is a possible cause.",
            "Use View report to identify the named mod and check its version. If this began after "
            "a mod update, try restoring the previous backup.",
            "mods",
        )
    if any(
        value in lowered
        for value in (
            "invalid session",
            "authentication failed",
            "failed to refresh",
            "token has expired",
        )
    ):
        return _result(
            "Minecraft sign-in needs attention",
            "The error reports an authentication or session failure.",
            "Sign in to your Microsoft profile again in Profiles and retry the launch.",
        )
    return _result(
        "Minecraft could not start",
        "The available error does not identify a specific cause.",
        "Use View report to inspect the latest log. If this started after a mod or loader change, "
        "restore the backup from before that change.",
    )


def diagnose_launch(instance_root, detail="", crash_report=None):
    parts = [str(detail)]
    root = Path(instance_root)
    paths = [Path(crash_report)] if crash_report else []
    launch_log = root / "latest-launch.log"
    game_log = root / "minecraft" / "logs" / "latest.log"
    paths.append(launch_log)
    try:
        if game_log.stat().st_mtime >= launch_log.stat().st_mtime:
            paths.append(game_log)
    except OSError:
        pass
    for path in paths:
        try:
            with path.open("rb") as source:
                source.seek(0, 2)
                size = source.tell()
                source.seek(max(0, size - 256 * 1024))
                parts.append(source.read(256 * 1024).decode("utf-8", "replace"))
        except OSError:
            continue
    return diagnose_text("\n".join(parts))
