"""Minecraft installation and launch support for BreakBlocks Launcher."""

from __future__ import annotations

import concurrent.futures
import json
import os
import pathlib
import platform
import re
import shlex
import subprocess
import tarfile
import threading
import urllib.request
import xml.etree.ElementTree as ET
import zipfile
from collections.abc import Callable, Iterable, Sequence
from typing import Any

from app_config import APP_NAME, APP_USER_AGENT, APP_VERSION_NUMBER
from process_environment import system_process_environment

VERSION_MANIFEST_URL = "https://piston-meta.mojang.com/mc/game/version_manifest_v2.json"
MOJANG_LIBRARIES_URL = "https://libraries.minecraft.net"
MOJANG_RESOURCES_URL = "https://resources.download.minecraft.net"

SYSTEM_OS = "windows" if os.name == "nt" else "linux"
MACHINE = platform.machine().lower()
SYSTEM_ARCH = (
    "x86_64"
    if MACHINE in {"amd64", "x86_64"}
    else "x86" if MACHINE in {"x86", "i386", "i686"} else MACHINE
)

ProgressCallback = Callable[[int, str], None]
DownloadJob = tuple[str, pathlib.Path, str, Sequence[str] | None]
LAUNCH_LOG_NAMES = ("latest-launch.log", "latest-launch-1.log", "latest-launch-2.log")


def linux_minecraft_window_class(version: str) -> str:
    """Return the WM_CLASS used by Minecraft's Linux game window."""
    return f"Minecraft* {str(version).strip()}"


def register_linux_minecraft_desktop(version: str) -> pathlib.Path | None:
    """Register a hidden desktop identity so GNOME can resolve Minecraft's icon."""
    if SYSTEM_OS != "linux":
        return None
    version = str(version).strip()
    slug = re.sub(r"[^a-z0-9]+", "-", version.casefold()).strip("-") or "game"
    applications = (
        pathlib.Path(os.environ.get("XDG_DATA_HOME", pathlib.Path.home() / ".local/share"))
        / "applications"
    )
    applications.mkdir(parents=True, exist_ok=True)
    desktop_file = applications / f"breakblocks-minecraft-{slug}.desktop"
    icon = pathlib.Path(__file__).resolve().parent / "assets/instance_icons/grass_block.png"
    window_class = linux_minecraft_window_class(version)
    content = (
        "[Desktop Entry]\n"
        "Type=Application\n"
        f"Name=Minecraft {version}\n"
        "Comment=Minecraft launched by BreakBlocks Launcher\n"
        "Exec=breakblocks-launcher\n"
        f"Icon={icon}\n"
        "Terminal=false\n"
        "NoDisplay=true\n"
        f"StartupWMClass={window_class}\n"
        "Categories=Game;\n"
    )
    try:
        if not desktop_file.is_file() or desktop_file.read_text(encoding="utf-8") != content:
            desktop_file.write_text(content, encoding="utf-8")
            os.chmod(desktop_file, 0o644)
    except OSError:
        return None
    return desktop_file


def rules_allowed(rules: Sequence[dict[str, Any]] | None) -> bool:
    """Evaluate the subset of Mojang launch rules supported by the launcher."""
    if not rules:
        return True

    allowed = False
    for rule in rules:
        os_rule = rule.get("os", {})
        os_matches = os_rule.get("name") in (None, SYSTEM_OS)
        if os_rule.get("arch") and os_rule["arch"] != SYSTEM_ARCH:
            os_matches = False
        features_match = all(not wanted for wanted in rule.get("features", {}).values())
        if os_matches and features_match:
            allowed = rule.get("action") == "allow"
    return allowed


class Installer:
    """Install a self-contained Minecraft launch profile for one instance."""

    def __init__(
        self,
        root: str | pathlib.Path,
        progress: ProgressCallback | None = None,
        java_override: str = "auto",
    ) -> None:
        self.root = pathlib.Path(root)
        self.progress = progress or (lambda _percent, _label: None)
        self.java_override = java_override

    def get_json(self, url: str) -> Any:
        request = urllib.request.Request(url, headers={"User-Agent": APP_USER_AGENT})
        with urllib.request.urlopen(request, timeout=45) as response:
            return json.load(response)

    def download(
        self,
        url: str,
        path: str | pathlib.Path,
        label: str = "Downloading",
        start: int = 0,
        end: int = 99,
        report: bool = True,
    ) -> None:
        target = pathlib.Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.is_file() and target.stat().st_size:
            if report:
                self.progress(end, label)
            return

        request = urllib.request.Request(url, headers={"User-Agent": APP_USER_AGENT})
        temporary = target.with_suffix(f"{target.suffix}.part")
        try:
            with urllib.request.urlopen(request, timeout=60) as source:
                total_size = int(source.headers.get("Content-Length", 0))
                received = 0
                with temporary.open("wb") as destination:
                    while block := source.read(128 * 1024):
                        destination.write(block)
                        received += len(block)
                        if total_size and report:
                            percent = start + int((end - start) * received / total_size)
                            self.progress(min(end, percent), label)
            temporary.replace(target)
        except Exception:
            temporary.unlink(missing_ok=True)
            raise

        if report:
            self.progress(end, label)

    def download_many(
        self,
        jobs: Iterable[DownloadJob],
        label: str,
        start: int,
        end: int,
        workers: int = 10,
    ) -> None:
        unique_jobs = {str(pathlib.Path(job[1])): job for job in jobs}
        pending = list(unique_jobs.values())
        if not pending:
            self.progress(end, label)
            return

        completed = 0
        progress_lock = threading.Lock()

        def fetch(job: DownloadJob) -> None:
            nonlocal completed
            url, target = job[:2]
            self.download(url, target, label, start, end, report=False)
            with progress_lock:
                completed += 1
                done = completed
            percent = start + int((end - start) * done / len(pending))
            self.progress(percent, f"{label} {done}/{len(pending)}")

        worker_count = min(workers, len(pending))
        with concurrent.futures.ThreadPoolExecutor(
            max_workers=worker_count,
            thread_name_prefix="breakblocks-download",
        ) as pool:
            futures = [pool.submit(fetch, job) for job in pending]
            for future in concurrent.futures.as_completed(futures):
                future.result()

    def install(self, instance: str | pathlib.Path, version: str, loader: str) -> dict[str, Any]:
        instance_root = pathlib.Path(instance)
        game_directory = instance_root / "minecraft"
        game_directory.mkdir(parents=True, exist_ok=True)

        shared = self.root / "minecraft-data"
        versions = shared / "versions"
        libraries = shared / "libraries"
        assets = shared / "assets"
        natives = game_directory / "natives"
        natives.mkdir(exist_ok=True)

        self.progress(1, "Loading Minecraft catalogue")
        manifest = self.get_json(VERSION_MANIFEST_URL)
        version_entry = next(
            (entry for entry in manifest["versions"] if entry["id"] == version),
            None,
        )
        if version_entry is None:
            raise RuntimeError("Minecraft version is not in Mojang's catalogue")

        metadata_path = versions / version / f"{version}.json"
        self.download(version_entry["url"], metadata_path, "Version information", 1, 3)
        base_profile = json.loads(metadata_path.read_text(encoding="utf-8"))
        launch_profile = base_profile

        java_major = base_profile.get("javaVersion", {}).get("majorVersion", 8)
        java = self.java(java_major, 3, 13)
        if loader == "Fabric":
            self.progress(13, "Loading Fabric profile")
            launch_profile = self.fabric(version, base_profile)
            self.progress(19, "Fabric profile ready")
        elif loader == "Quilt":
            self.progress(13, "Loading Quilt profile")
            launch_profile = self.quilt(version, base_profile)
            self.progress(19, "Quilt profile ready")
        elif loader == "Forge":
            launch_profile = self.forge(version, base_profile, shared, java)
        elif loader == "NeoForge":
            launch_profile = self.neoforge(version, base_profile, shared, java)
        elif loader == "Vanilla":
            self.progress(19, "Vanilla profile ready")
        else:
            raise RuntimeError(f"Unsupported loader: {loader}")

        client = versions / version / f"{version}.jar"
        self.download(
            base_profile["downloads"]["client"]["url"], client, "Minecraft client", 20, 30
        )

        classpath: list[str] = []
        library_jobs: list[DownloadJob] = []
        for library in launch_profile.get("libraries", []):
            if not rules_allowed(library.get("rules")):
                continue

            downloads = library.get("downloads", {})
            artifact = downloads.get("artifact")
            if artifact:
                target = libraries / artifact["path"]
                url = artifact.get("url") or self.maven_url(library["name"])
                library_jobs.append((url, target, "Libraries", None))
                classpath.append(str(target))
            elif library.get("name"):
                relative_path = self.maven_path(library["name"])
                target = libraries / relative_path
                repository = library.get("url", f"{MOJANG_LIBRARIES_URL}/")
                library_jobs.append(
                    (f"{repository.rstrip('/')}/{relative_path}", target, "Libraries", None)
                )
                classpath.append(str(target))

            classifier = self.native_classifier(library)
            native_artifact = downloads.get("classifiers", {}).get(classifier)
            if classifier and native_artifact:
                target = libraries / native_artifact["path"]
                exclusions = library.get("extract", {}).get("exclude", [])
                library_jobs.append(
                    (native_artifact["url"], target, "Native libraries", exclusions)
                )

        self.download_many(library_jobs, "Libraries", 31, 50, workers=8)
        for _url, target, _label, exclusions in library_jobs:
            if exclusions is not None:
                self.extract_natives(target, natives, exclusions)

        classpath.append(str(client))
        asset_index = base_profile["assetIndex"]
        asset_index_path = assets / "indexes" / f"{asset_index['id']}.json"
        self.download(asset_index["url"], asset_index_path, "Asset index", 50, 52)
        asset_objects = json.loads(asset_index_path.read_text(encoding="utf-8")).get("objects", {})
        asset_jobs: list[DownloadJob] = []
        for asset in asset_objects.values():
            digest = asset["hash"]
            asset_jobs.append(
                (
                    f"{MOJANG_RESOURCES_URL}/{digest[:2]}/{digest}",
                    assets / "objects" / digest[:2] / digest,
                    "Assets",
                    None,
                )
            )
        self.download_many(asset_jobs, "Assets", 52, 99, workers=12)

        record = {
            "version": version,
            "loader": loader,
            "java": str(java),
            "javaMajor": java_major,
            "mainClass": launch_profile["mainClass"],
            "classpath": classpath,
            "assets": str(assets),
            "assetIndex": asset_index["id"],
            "versionType": base_profile.get("type", "release"),
            "arguments": launch_profile.get("arguments", {}),
            "legacyArguments": launch_profile.get("minecraftArguments", ""),
            "natives": str(natives),
            "client": str(client),
        }
        launch_record = instance_root / "instance-launch.json"
        launch_record.write_text(json.dumps(record, indent=2), encoding="utf-8")
        self.progress(100, "Installed successfully")
        return record

    def fabric(self, version: str, base_profile: dict[str, Any]) -> dict[str, Any]:
        loaders = self.get_json(f"https://meta.fabricmc.net/v2/versions/loader/{version}")
        if not loaders:
            raise RuntimeError(f"Fabric is not available for {version}")
        loader_version = loaders[0]["loader"]["version"]
        profile = self.get_json(
            f"https://meta.fabricmc.net/v2/versions/loader/{version}/{loader_version}/profile/json"
        )
        return self.merge_profiles(base_profile, profile)

    def quilt(self, version: str, base_profile: dict[str, Any]) -> dict[str, Any]:
        loaders = self.get_json(f"https://meta.quiltmc.org/v3/versions/loader/{version}")
        if not loaders:
            raise RuntimeError(f"Quilt is not available for {version}")
        loader_version = loaders[0]["loader"]["version"]
        profile = self.get_json(
            f"https://meta.quiltmc.org/v3/versions/loader/{version}/{loader_version}/profile/json"
        )
        return self.merge_profiles(base_profile, profile)

    def forge(
        self,
        version: str,
        base_profile: dict[str, Any],
        shared: pathlib.Path,
        java: pathlib.Path,
    ) -> dict[str, Any]:
        promotions = self.get_json(
            "https://files.minecraftforge.net/net/minecraftforge/forge/promotions_slim.json"
        ).get("promos", {})
        build = promotions.get(f"{version}-recommended") or promotions.get(f"{version}-latest")
        if not build:
            raise RuntimeError(f"Forge is not available for {version}")
        coordinate = f"{version}-{build}"
        url = (
            "https://maven.minecraftforge.net/net/minecraftforge/forge/"
            f"{coordinate}/forge-{coordinate}-installer.jar"
        )
        return self.run_installer(url, base_profile, shared, java, "forge")

    def neoforge(
        self,
        version: str,
        base_profile: dict[str, Any],
        shared: pathlib.Path,
        java: pathlib.Path,
    ) -> dict[str, Any]:
        metadata_url = (
            "https://maven.neoforged.net/releases/net/neoforged/neoforge/maven-metadata.xml"
        )
        request = urllib.request.Request(metadata_url, headers={"User-Agent": APP_USER_AGENT})
        with urllib.request.urlopen(request, timeout=30) as response:
            metadata = response.read()
        available = [node.text for node in ET.fromstring(metadata).iter("version") if node.text]
        prefix = version[2:] if version.startswith("1.") else version
        matching = [candidate for candidate in available if candidate.startswith(f"{prefix}.")]
        if not matching:
            raise RuntimeError(f"NeoForge is not available for {version}")
        build = matching[-1]
        url = (
            "https://maven.neoforged.net/releases/net/neoforged/neoforge/"
            f"{build}/neoforge-{build}-installer.jar"
        )
        return self.run_installer(url, base_profile, shared, java, "neoforge")

    def run_installer(
        self,
        url: str,
        base_profile: dict[str, Any],
        shared: pathlib.Path,
        java: pathlib.Path,
        kind: str,
    ) -> dict[str, Any]:
        shared.mkdir(parents=True, exist_ok=True)
        (shared / "launcher_profiles.json").write_text(
            '{"profiles":{},"settings":{}}', encoding="utf-8"
        )
        existing_profiles = set((shared / "versions").glob("*/*.json"))
        installer = shared / "installers" / f"{kind}-installer.jar"
        title = kind.title()
        self.download(url, installer, f"{title} installer", 13, 16)
        self.progress(17, f"Running {title} installer")

        creation_flags = getattr(subprocess, "CREATE_NO_WINDOW", 0) if SYSTEM_OS == "windows" else 0
        result = subprocess.run(
            [str(java), "-jar", str(installer), "--installClient", str(shared)],
            capture_output=True,
            text=True,
            env=system_process_environment(),
            timeout=300,
            creationflags=creation_flags,
            check=False,
        )
        if result.returncode:
            detail = (result.stderr or result.stdout)[-800:]
            raise RuntimeError(f"{title} installer failed: {detail}")

        current_profiles = set((shared / "versions").glob("*/*.json"))
        candidates = list(current_profiles - existing_profiles) or [
            path for path in current_profiles if kind in path.as_posix().lower()
        ]
        if not candidates:
            raise RuntimeError(f"{title} did not create a launch profile")
        newest = max(candidates, key=lambda path: path.stat().st_mtime)
        profile = json.loads(newest.read_text(encoding="utf-8"))
        self.progress(19, f"{title} profile ready")
        return self.merge_profiles(base_profile, profile)

    @staticmethod
    def merge_profiles(base: dict[str, Any], extra: dict[str, Any]) -> dict[str, Any]:
        merged = dict(base)
        merged["mainClass"] = extra.get("mainClass", base["mainClass"])
        merged["libraries"] = base.get("libraries", []) + extra.get("libraries", [])
        merged["arguments"] = {
            argument_type: base.get("arguments", {}).get(argument_type, [])
            + extra.get("arguments", {}).get(argument_type, [])
            for argument_type in ("game", "jvm")
        }
        return merged

    @staticmethod
    def maven_url(name: str) -> str:
        group, artifact, version = name.split(":")[:3]
        group_path = group.replace(".", "/")
        return f"{MOJANG_LIBRARIES_URL}/{group_path}/{artifact}/{version}/{artifact}-{version}.jar"

    @staticmethod
    def maven_path(name: str) -> str:
        parts = name.split(":")
        group, artifact, version = parts[:3]
        classifier = f"-{parts[3]}" if len(parts) > 3 else ""
        group_path = group.replace(".", "/")
        return f"{group_path}/{artifact}/{version}/{artifact}-{version}{classifier}.jar"

    @staticmethod
    def native_classifier(library: dict[str, Any]) -> str | None:
        value = library.get("natives", {}).get(SYSTEM_OS)
        bits = "64" if SYSTEM_ARCH == "x86_64" else "32"
        return value.replace("${arch}", bits) if value else None

    @staticmethod
    def extract_natives(
        archive: str | pathlib.Path,
        target: str | pathlib.Path,
        exclusions: Sequence[str],
    ) -> None:
        target_root = pathlib.Path(target).resolve()
        with zipfile.ZipFile(archive) as source:
            for member in source.infolist():
                name = member.filename
                if (
                    member.is_dir()
                    or name.startswith("META-INF/")
                    or any(name.startswith(prefix) for prefix in exclusions)
                ):
                    continue
                destination = (target_root / name).resolve()
                if target_root not in destination.parents:
                    raise RuntimeError(f"Unsafe native-library path: {name}")
                destination.parent.mkdir(parents=True, exist_ok=True)
                with source.open(member) as input_file, destination.open("wb") as output_file:
                    while block := input_file.read(128 * 1024):
                        output_file.write(block)

    def java(self, major: int, start: int = 5, end: int = 15) -> pathlib.Path:
        if self.java_override and self.java_override != "auto":
            candidate = pathlib.Path(self.java_override).expanduser()
            if not candidate.is_file():
                raise RuntimeError("The configured Java executable was not found")
            return candidate

        executable = "java.exe" if SYSTEM_OS == "windows" else "java"
        managed = self.root / "java" / str(major)
        managed_candidates = list(managed.glob(f"**/bin/{executable}"))
        if managed_candidates:
            return managed_candidates[0]

        system_java = self._matching_system_java(executable, major)
        if system_java is not None:
            return system_java

        architecture = (
            "x64" if SYSTEM_ARCH == "x86_64" else "x86" if SYSTEM_ARCH == "x86" else SYSTEM_ARCH
        )
        self.progress(start, f"Downloading Java {major}")
        assets = self.get_json(
            "https://api.adoptium.net/v3/assets/latest/"
            f"{major}/hotspot?architecture={architecture}&image_type=jre"
            f"&os={SYSTEM_OS}&vendor=eclipse"
        )
        if not assets:
            raise RuntimeError("No Java runtime download was found")

        package = assets[0]["binary"]["package"]
        archive = managed / package["name"]
        self.download(package["link"], archive, "Java runtime", start, end)
        managed.mkdir(parents=True, exist_ok=True)
        if archive.suffix.lower() == ".zip":
            self._safe_extract_zip(archive, managed)
        else:
            self._safe_extract_tar(archive, managed)

        installed = list(managed.glob(f"**/bin/{executable}"))
        if not installed:
            raise RuntimeError("Downloaded Java runtime is incomplete")
        installed[0].chmod(0o755)
        return installed[0]

    @staticmethod
    def _matching_system_java(executable: str, major: int) -> pathlib.Path | None:
        creation_flags = getattr(subprocess, "CREATE_NO_WINDOW", 0) if SYSTEM_OS == "windows" else 0
        try:
            output = subprocess.check_output(
                [executable, "-version"],
                stderr=subprocess.STDOUT,
                text=True,
                env=system_process_environment(),
                creationflags=creation_flags,
            )
        except (OSError, subprocess.SubprocessError):
            return None
        match = re.search(r'version "(?:1\.)?(\d+)', output)
        if match and int(match.group(1)) == major:
            return pathlib.Path(executable)
        return None

    @staticmethod
    def _safe_extract_zip(archive: pathlib.Path, target: pathlib.Path) -> None:
        target_root = target.resolve()
        with zipfile.ZipFile(archive) as source:
            for member in source.infolist():
                destination = (target_root / member.filename).resolve()
                if destination != target_root and target_root not in destination.parents:
                    raise RuntimeError(f"Unsafe Java archive path: {member.filename}")
            # Every member path has been resolved and confined to target_root above.
            source.extractall(target_root)  # nosec B202

    @staticmethod
    def _safe_extract_tar(archive: pathlib.Path, target: pathlib.Path) -> None:
        target_root = target.resolve()
        with tarfile.open(archive) as source:
            for member in source.getmembers():
                destination = (target_root / member.name).resolve()
                if destination != target_root and target_root not in destination.parents:
                    raise RuntimeError(f"Unsafe Java archive path: {member.name}")
                if member.issym() or member.islnk():
                    link_target = (destination.parent / member.linkname).resolve()
                    if link_target != target_root and target_root not in link_target.parents:
                        raise RuntimeError(f"Unsafe Java archive link: {member.name}")
            # Every member path and link target has been confined to target_root above.
            source.extractall(target_root)  # nosec B202


def rotate_launch_logs(instance: str | pathlib.Path) -> pathlib.Path:
    """Keep the current launch log and the two preceding logs for an instance."""
    instance_root = pathlib.Path(instance)
    paths = [instance_root / name for name in LAUNCH_LOG_NAMES]
    for index in range(len(paths) - 1, 0, -1):
        source = paths[index - 1]
        destination = paths[index]
        if source.is_file():
            os.replace(source, destination)
        else:
            destination.unlink(missing_ok=True)
    return paths[0]


def newest_crash_report(
    instance: str | pathlib.Path, launched_at: float | None = None
) -> pathlib.Path | None:
    """Return the newest Minecraft crash report created by the current session."""
    report_directory = pathlib.Path(instance) / "minecraft" / "crash-reports"
    try:
        reports = [path for path in report_directory.glob("*.txt") if path.is_file()]
        if not reports:
            return None
        newest = max(reports, key=lambda path: path.stat().st_mtime)
        if launched_at is not None and newest.stat().st_mtime < float(launched_at) - 2:
            return None
        return newest
    except OSError:
        return None


def launch_log_indicates_clean_shutdown(instance: str | pathlib.Path) -> bool:
    """Return whether the current launch log records an orderly game shutdown.

    Some Windows Java/LWJGL combinations return a non-zero process status when
    the player closes the game with the title-bar X. Minecraft still writes its
    normal ``Stopping!`` message in that case, so the launcher should not show a
    crash dialog unless the session also produced genuine crash evidence.
    """
    log_path = pathlib.Path(instance) / LAUNCH_LOG_NAMES[0]
    try:
        with log_path.open("rb") as stream:
            stream.seek(0, os.SEEK_END)
            size = stream.tell()
            stream.seek(max(0, size - 256 * 1024))
            text = stream.read().decode("utf-8", errors="replace")
    except OSError:
        return False

    lowered = text.casefold()
    crash_markers = (
        "---- minecraft crash report ----",
        "unreported exception thrown!",
        "game crashed! crash report saved to:",
        "a fatal error has been detected by the java runtime environment",
    )
    if any(marker in lowered for marker in crash_markers):
        return False
    return any(
        marker in lowered
        for marker in (
            "[render thread/info]: stopping!",
            "[client thread/info]: stopping!",
        )
    )


def launch(instance: str | pathlib.Path, account: dict[str, Any]) -> subprocess.Popen[Any]:
    """Start Minecraft for an installed instance and return its process handle."""
    instance_root = pathlib.Path(instance)
    launch_record = json.loads((instance_root / "instance-launch.json").read_text(encoding="utf-8"))
    game_directory = instance_root / "minecraft"
    game_directory.mkdir(exist_ok=True)

    substitutions = {
        "${auth_player_name}": account["name"],
        "${version_name}": launch_record["version"],
        "${game_directory}": str(game_directory),
        "${assets_root}": launch_record["assets"],
        "${assets_index_name}": launch_record["assetIndex"],
        "${auth_uuid}": account["id"].replace("-", ""),
        "${auth_access_token}": account.get("minecraft_token", "0"),
        "${clientid}": "",
        "${auth_xuid}": "",
        "${user_type}": "msa" if account["type"] == "Microsoft" else "legacy",
        "${version_type}": launch_record["versionType"],
        "${natives_directory}": launch_record["natives"],
        "${launcher_name}": APP_NAME,
        "${launcher_version}": APP_VERSION_NUMBER,
        "${classpath}": os.pathsep.join(launch_record["classpath"]),
        "${classpath_separator}": os.pathsep,
        "${library_directory}": str(pathlib.Path(launch_record["assets"]).parent / "libraries"),
    }

    def expand(value: str) -> str:
        for placeholder, replacement in substitutions.items():
            value = value.replace(placeholder, replacement)
        return value

    def append_argument(target: list[str], item: str | dict[str, Any]) -> None:
        if isinstance(item, str):
            target.append(expand(item))
            return
        if rules_allowed(item.get("rules", [])):
            values = item.get("value", [])
            if isinstance(values, str):
                values = [values]
            target.extend(expand(value) for value in values)

    jvm_arguments: list[str] = []
    game_arguments: list[str] = []
    arguments = launch_record.get("arguments", {})
    for item in arguments.get("jvm", []):
        append_argument(jvm_arguments, item)
    for item in arguments.get("game", []):
        append_argument(game_arguments, item)

    if not game_arguments and launch_record.get("legacyArguments"):
        game_arguments = [expand(value) for value in shlex.split(launch_record["legacyArguments"])]
    if not any(value.startswith("-Djava.library.path") for value in jvm_arguments):
        jvm_arguments.append(f"-Djava.library.path={launch_record['natives']}")
    if "-cp" not in jvm_arguments and "-classpath" not in jvm_arguments:
        jvm_arguments.extend(["-cp", os.pathsep.join(launch_record["classpath"])])

    memory = int(account.get("memory", 4096))
    command = [
        launch_record["java"],
        f"-Xmx{memory}M",
        *jvm_arguments,
        launch_record["mainClass"],
        *game_arguments,
    ]
    process_environment = system_process_environment()
    if SYSTEM_OS == "linux":
        window_class = linux_minecraft_window_class(launch_record["version"])
        process_environment["AWT_WM_CLASS"] = window_class
        register_linux_minecraft_desktop(launch_record["version"])
    creation_flags = getattr(subprocess, "CREATE_NO_WINDOW", 0) if SYSTEM_OS == "windows" else 0
    log_handle = rotate_launch_logs(instance_root).open("w", encoding="utf-8")
    try:
        return subprocess.Popen(
            command,
            cwd=game_directory,
            stdout=log_handle,
            stderr=subprocess.STDOUT,
            env=process_environment,
            creationflags=creation_flags,
        )
    finally:
        log_handle.close()
