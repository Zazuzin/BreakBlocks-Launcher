"""Exercise moved launch profiles and pre-launch errors without downloading Minecraft."""

import json
import sys
import tempfile
import zipfile
from pathlib import Path
from unittest.mock import patch

import launch_diagnostics
import minecraft_backend as backend

ACCOUNT = {
    "id": "player-id",
    "name": "Player",
    "type": "Microsoft",
    "minecraft_token": "secret-test-access-token",
}


def installed_instance(root):
    instance = root / "instances" / "example"
    natives = instance / "minecraft" / "natives"
    natives.mkdir(parents=True)
    assets = root / "minecraft-data" / "assets"
    index = assets / "indexes" / "test.json"
    client = root / "minecraft-data" / "versions" / "test" / "test.jar"
    library = root / "minecraft-data" / "libraries" / "example.jar"
    for path in (index, client, library):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"fixture")
    record = {
        "version": "test",
        "loader": "Vanilla",
        "java": str(Path(sys.executable).resolve()),
        "javaMajor": 21,
        "assets": str(assets),
        "assetIndex": "test",
        "versionType": "release",
        "natives": str(natives),
        "client": str(client),
        "classpath": [str(library), str(client)],
        "mainClass": "net.minecraft.client.Main",
        "arguments": {
            "jvm": [f"-Dexample.path={library}"],
            "game": ["--accessToken", "${auth_access_token}"],
        },
        "legacyArguments": "",
    }
    (instance / "instance-launch.json").write_text(json.dumps(record), encoding="utf-8")
    return instance, record


def read_record(instance):
    return json.loads((instance / "instance-launch.json").read_text(encoding="utf-8"))


def launch_failure(instance, expected, **options):
    with patch.object(backend.subprocess, "Popen") as start:
        try:
            backend.launch(instance, ACCOUNT, **options)
        except RuntimeError as error:
            assert expected in str(error), str(error)
            assert ACCOUNT["minecraft_token"] not in str(error)
            assert launch_diagnostics.diagnose_text(error)["action"] == "repair"
            start.assert_not_called()
            return str(error)
        raise AssertionError("A broken launch profile started a process")


def test_moved_data_paths_are_rebased_and_saved_before_launch():
    with tempfile.TemporaryDirectory() as temporary:
        base = Path(temporary).resolve()
        old_root = base / "Zazu Launcher"
        instance, original = installed_instance(old_root)
        java = old_root / "java" / "21" / "runtime" / "bin" / "java.exe"
        java.parent.mkdir(parents=True)
        java.write_bytes(b"java fixture")
        original["java"] = str(java)
        original["arguments"]["jvm"].append(
            "-Dforward.path=" + Path(original["classpath"][0]).as_posix()
        )
        original["description"] = str(old_root)  # Non-path metadata is untouched.
        (instance / "instance-launch.json").write_text(json.dumps(original))
        world = instance / "minecraft" / "saves" / "world" / "level.dat"
        world.parent.mkdir(parents=True)
        world.write_bytes(b"world data")
        current_root = base / "BreakBlocks Launcher"
        old_root.rename(current_root)
        instance = current_root / "instances" / "example"

        with patch.object(backend.subprocess, "Popen") as start:
            backend.launch(instance, ACCOUNT)
            command = start.call_args.args[0]
            assert command[0] == str(current_root / java.relative_to(old_root))
            assert (
                f"-Dexample.path={current_root / Path(original['classpath'][0]).relative_to(old_root)}"
                in command
            )
            assert any(value.startswith("-Dforward.path=" + str(current_root)) for value in command)
            assert start.call_args.kwargs["cwd"] == instance / "minecraft"
        updated = read_record(instance)
        assert updated["description"] == original["description"]
        assert updated["assets"] == str(current_root / "minecraft-data" / "assets")
        assert backend.relocate_launch_record(updated, instance) == updated
        assert (current_root / world.relative_to(old_root)).read_bytes() == b"world data"
        assert not (instance / "instance-launch.json.tmp").exists()


def test_relocation_leaves_external_java_and_similarly_named_roots_alone():
    with tempfile.TemporaryDirectory() as temporary:
        base = Path(temporary).resolve()
        old_root = base / "old"
        instance, record = installed_instance(old_root)
        record["classpath"].append(str(base / "old-other" / "external.jar"))
        nested_external = str(base / "external" / Path(*old_root.parts[1:]) / "external.jar")
        record["classpath"].append(nested_external)
        record["arguments"]["jvm"].append("-Dexternal=" + nested_external)
        record["legacyArguments"] = f'--gameDir "{instance / "minecraft"}"'
        updated = backend.relocate_launch_record(record, base / "new" / "instances" / "example")
        assert updated["java"] == record["java"]
        assert updated["classpath"][-1] == record["classpath"][-1]
        assert updated["classpath"][-2] == record["classpath"][-2]
        assert updated["arguments"]["jvm"][-1] == record["arguments"]["jvm"][-1]
        assert (
            str(base / "new" / "instances" / "example" / "minecraft") in updated["legacyArguments"]
        )
        assert record["assets"] == str(old_root / "minecraft-data" / "assets")


def test_java_is_selected_using_current_settings_and_required_major():
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary).resolve()
        instance, record = installed_instance(root)
        record["java"] = str(root / "removed-java.exe")
        (instance / "instance-launch.json").write_text(json.dumps(record))

        def progress(_percent, _label):
            pass

        for selected in ("auto", sys.executable):
            with (
                patch.object(backend, "Installer") as installer,
                patch.object(backend.subprocess, "Popen") as start,
            ):
                installer.return_value.java.return_value = Path(sys.executable)
                backend.launch(instance, ACCOUNT, java_override=selected, progress=progress)
                installer.assert_called_once_with(root.resolve(), progress, selected)
                installer.return_value.java.assert_called_once_with(21)
                assert start.call_args.args[0][0] == str(Path(sys.executable).resolve())
        assert read_record(instance)["java"] == str(Path(sys.executable).resolve())


def test_system_java_is_checked_and_stored_as_an_absolute_path():
    with (
        patch.object(backend.shutil, "which", return_value=sys.executable) as lookup,
        patch.object(
            backend.subprocess, "check_output", return_value='openjdk version "21.0.7"'
        ) as check,
    ):
        found = backend.Installer._matching_system_java("java.exe", 21)
        assert found == Path(sys.executable).resolve()
        assert check.call_args.args[0] == [str(found), "-version"]
        assert check.call_args.kwargs["timeout"] == 15
        lookup.assert_called_once()
    with patch.object(backend.shutil, "which", return_value=None):
        assert backend.Installer._matching_system_java("java.exe", 21) is None
    with (
        patch.object(backend.shutil, "which", return_value=sys.executable),
        patch.object(backend.subprocess, "check_output", return_value='java version "1.8.0_401"'),
    ):
        assert backend.Installer._matching_system_java("java", 21) is None


def test_auto_java_uses_moved_managed_runtime_without_network():
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary).resolve()
        executable = "java.exe" if backend.SYSTEM_OS == "windows" else "java"
        runtime = root / "java" / "21" / "runtime" / "bin" / executable
        runtime.parent.mkdir(parents=True)
        runtime.write_bytes(b"fixture")
        with patch.object(backend.Installer, "get_json") as network:
            assert backend.Installer(root).java(21) == runtime.resolve()
            network.assert_not_called()


def test_auto_java_downloads_a_runtime_when_the_old_system_java_is_gone():
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary).resolve()
        instance, record = installed_instance(root)
        record["java"] = str(root / "removed-system-java.exe")
        (instance / "instance-launch.json").write_text(json.dumps(record))
        executable = "java.exe" if backend.SYSTEM_OS == "windows" else "java"

        def download(_installer, _url, target, *_args):
            target.parent.mkdir(parents=True, exist_ok=True)
            with zipfile.ZipFile(target, "w") as archive:
                archive.writestr("runtime/bin/" + executable, b"java fixture")

        with (
            patch.object(backend.Installer, "_matching_system_java", return_value=None),
            patch.object(
                backend.Installer,
                "get_json",
                return_value=[
                    {
                        "binary": {
                            "package": {
                                "name": "runtime.zip",
                                "link": "https://example.invalid/runtime.zip",
                            }
                        }
                    }
                ],
            ) as metadata,
            patch.object(backend.Installer, "download", download),
            patch.object(backend.subprocess, "Popen") as start,
        ):
            backend.launch(instance, ACCOUNT, java_override="auto")
            metadata.assert_called_once()
            selected = root / "java" / "21" / "runtime" / "bin" / executable
            assert selected.is_file()
            assert start.call_args.args[0][0] == str(selected.resolve())
        assert read_record(instance)["java"] == str(selected.resolve())


def test_missing_java_names_the_runtime_without_starting_minecraft():
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary).resolve()
        instance, record = installed_instance(root)
        record["java"] = str(root / "missing" / "java.exe")
        (instance / "instance-launch.json").write_text(json.dumps(record))
        detail = launch_failure(instance, "The selected Java executable was not found")
        assert record["java"] in detail


def test_missing_installation_files_are_named_before_java_selection():
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary).resolve()
        instance, record = installed_instance(root)
        Path(record["classpath"][0]).unlink()
        with patch.object(backend, "Installer") as installer:
            detail = launch_failure(
                instance, "Minecraft installation files are missing", java_override="auto"
            )
            installer.assert_not_called()
        assert record["classpath"][0] in detail


def test_missing_or_damaged_profile_offers_repair():
    with tempfile.TemporaryDirectory() as temporary:
        instance, _record = installed_instance(Path(temporary).resolve())
        profile = instance / "instance-launch.json"
        profile.unlink()
        launch_failure(instance, "The instance launch profile is missing")
        profile.write_text("{bad json")
        launch_failure(instance, "The instance launch profile is damaged")


def test_process_start_error_keeps_paths_but_excludes_account_tokens():
    with tempfile.TemporaryDirectory() as temporary:
        instance, record = installed_instance(Path(temporary).resolve())
        with patch.object(
            backend.subprocess,
            "Popen",
            side_effect=FileNotFoundError("[WinError 2] The system cannot find the file specified"),
        ) as start:
            try:
                backend.launch(instance, ACCOUNT)
            except RuntimeError as error:
                detail = str(error)
                assert "Minecraft could not start its Java process" in detail
                assert "[WinError 2]" in detail
                assert record["java"] in detail
                assert str(instance / "minecraft") in detail
                assert ACCOUNT["minecraft_token"] not in detail
                assert launch_diagnostics.diagnose_text(detail)["action"] == "repair"
            else:
                raise AssertionError("A process start error was swallowed")
            assert start.call_args.kwargs["stdout"].closed
        assert ACCOUNT["minecraft_token"] not in (instance / "latest-launch.log").read_text()


def test_real_child_starts_from_moved_data_folder_with_spaces():
    # Use Python as a harmless process shim. It accepts -X options; everything
    # after -c is script argv. This checks real cwd/argv/log handling on both OSes.
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary).resolve() / "Zazu Launcher"
        instance, record = installed_instance(root)
        record["arguments"]["jvm"] = [
            "-c",
            "import os; print('launch-shim-started'); print(os.getcwd())",
            "-Djava.library.path=${natives_directory}",
            "-cp",
            "${classpath}",
        ]
        (instance / "instance-launch.json").write_text(json.dumps(record))
        current = root.parent / "BreakBlocks Launcher"
        root.rename(current)
        instance = current / "instances" / "example"
        process = backend.launch(instance, ACCOUNT)
        assert process.wait(timeout=15) == 0
        output = (instance / "latest-launch.log").read_text()
        assert "launch-shim-started" in output
        assert str(instance / "minecraft") in output


if __name__ == "__main__":
    tests = [value for name, value in sorted(globals().items()) if name.startswith("test_")]
    for test in tests:
        test()
    print(f"Passed {len(tests)} Minecraft launch tests")
