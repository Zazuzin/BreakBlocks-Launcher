import tempfile
from pathlib import Path

import launch_diagnostics as diagnostics


def test_java_class_version_message_identifies_required_java():
    result = diagnostics.diagnose_text(
        "UnsupportedClassVersionError: mod/Main has been compiled by a more recent version of the Java Runtime (class file version 65.0), this version recognizes up to 61.0"
    )
    assert result["title"] == "Java version is too old"
    assert "Java 21" in result["explanation"]
    assert result["action"] == "repair"


def test_dependency_failure_explains_mod_management_and_restore():
    result = diagnostics.diagnose_text(
        "Incompatible mods found!\nMod 'Example' requires version 0.100 of fabric-api, which is missing!"
    )
    assert "Example" in result["explanation"]
    assert result["action"] == "mods" and "restore" in result["next_step"]


def test_memory_graphics_and_mixin_failures_have_separate_advice():
    assert (
        diagnostics.diagnose_text("java.lang.OutOfMemoryError: Java heap space")["action"] == "edit"
    )
    assert (
        "Graphics"
        in diagnostics.diagnose_text("GLFW error 65542: Driver does not support OpenGL")["title"]
    )
    result = diagnostics.diagnose_text("MixinApplyError: Mixin apply failed for mod.Example")
    assert result["action"] == "mods" and "possible cause" in result["explanation"]


def test_unknown_exit_does_not_invent_a_cause():
    result = diagnostics.diagnose_text("Process exited with code 1")
    assert "does not identify" in result["explanation"]
    assert result["action"] is None


def test_missing_java_and_launch_profile_offer_repair():
    assert (
        diagnostics.diagnose_text("[Errno 2] No such file or directory: '/runtime/bin/java'")[
            "action"
        ]
        == "repair"
    )
    assert (
        diagnostics.diagnose_text(
            "[Errno 2] No such file or directory: '/instance/instance-launch.json'"
        )["action"]
        == "repair"
    )


def test_old_minecraft_log_does_not_override_a_new_unknown_launch_failure():
    with tempfile.TemporaryDirectory() as temporary:
        import os

        root = Path(temporary)
        game_log = root / "minecraft/logs/latest.log"
        game_log.parent.mkdir(parents=True)
        game_log.write_text("Incompatible mods found!")
        os.utime(game_log, (100, 100))
        (root / "latest-launch.log").write_text("Process exited without a specific error")
        assert diagnostics.diagnose_launch(root)["action"] is None


def test_crash_report_and_end_of_large_launch_log_are_read():
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        (root / "latest-launch.log").write_text(
            "unrelated\n" * 100000 + "Could not find or load main class net.minecraft.client.Main"
        )
        assert diagnostics.diagnose_launch(root)["action"] == "repair"
        report = root / "crash.txt"
        report.write_text("Incompatible mods found! Mod 'Example' requires fabric-api")
        assert diagnostics.diagnose_launch(root, crash_report=report)["action"] == "mods"


if __name__ == "__main__":
    tests = [value for name, value in sorted(globals().items()) if name.startswith("test_")]
    for test in tests:
        test()
    print(f"Passed {len(tests)} launch diagnostic tests")
