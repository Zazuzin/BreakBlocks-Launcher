import hashlib
import io
import json
import pathlib
import tempfile
import urllib.parse
import zipfile
from unittest import mock

import mod_sources
import modrinth_client


class FakeResponse(io.BytesIO):
    pass


def fabric_jar(mod_id, name, version, minecraft="1.21.1", contact=None):
    output = io.BytesIO()
    metadata = {
        "schemaVersion": 1,
        "id": mod_id,
        "name": name,
        "version": version,
        "depends": {"minecraft": minecraft},
    }
    if contact:
        metadata["contact"] = contact
    with zipfile.ZipFile(output, "w") as archive:
        archive.writestr("fabric.mod.json", json.dumps(metadata))
    return output.getvalue()


class FakeSourceClient:
    def __init__(self):
        self.version = "1.0.0"

    def essential_latest(self, source_key, game_version):
        mod_id = "meteor-client" if source_key == "meteor-client" else "streak-addon"
        title = "Meteor Client" if source_key == "meteor-client" else "Trouser Streak"
        return {
            "provider": "meteor" if source_key == "meteor-client" else "github",
            "source_key": source_key,
            "title": title,
            "version_id": self.version,
            "version_number": self.version,
            "filename": f"{source_key}-{self.version}.jar",
            "url": "https://example.invalid/mod.jar",
            "game_version": game_version,
            "expected_mod_ids": [mod_id],
        }

    def generic_github_latest(self, _repo, game_version, record):
        return self.essential_latest(record.get("source_key", "trouser-streak"), game_version)

    def download(self, descriptor, destination, _progress):
        destination = pathlib.Path(destination)
        target = destination / descriptor["filename"]
        mod_id = descriptor["expected_mod_ids"][0]
        payload = fabric_jar(mod_id, descriptor["title"], descriptor["version_number"])
        target.write_bytes(payload)
        return (
            target,
            json.loads(zipfile.ZipFile(io.BytesIO(payload)).read("fabric.mod.json")),
            hashlib.sha512(payload).hexdigest(),
        )


class FakeClient:
    def __init__(self):
        self.payloads = {
            "main-v1.jar": b"main version one",
            "main-v2.jar": b"main version two",
            "dependency.jar": b"required dependency",
            "optional.jar": b"optional dependency",
        }
        self.projects = {
            "main": {"id": "main", "title": "Main Mod", "slug": "main-mod", "icon_url": None},
            "dependency": {
                "id": "dependency",
                "title": "Required Library",
                "slug": "required-library",
                "icon_url": None,
            },
            "optional": {
                "id": "optional",
                "title": "Optional Extra",
                "slug": "optional-extra",
                "icon_url": None,
            },
        }
        self.latest = {
            "main": self.make_version(
                "main",
                "main-v1",
                "1.0.0",
                "main-v1.jar",
                [
                    {
                        "project_id": "dependency",
                        "version_id": "dependency-v1",
                        "dependency_type": "required",
                    },
                    {
                        "project_id": "optional",
                        "version_id": "optional-v1",
                        "dependency_type": "optional",
                    },
                ],
            ),
            "dependency": self.make_version(
                "dependency", "dependency-v1", "1.0.0", "dependency.jar", []
            ),
            "optional": self.make_version("optional", "optional-v1", "1.0.0", "optional.jar", []),
        }
        self.by_version = {version["id"]: version for version in self.latest.values()}

    def make_version(self, project_id, version_id, version_number, filename, dependencies):
        payload = self.payloads[filename]
        return {
            "id": version_id,
            "project_id": project_id,
            "name": version_number,
            "version_number": version_number,
            "version_type": "release",
            "status": "listed",
            "environment": "client_and_server",
            "game_versions": ["1.21.1"],
            "loaders": ["fabric"],
            "dependencies": dependencies,
            "files": [
                {
                    "filename": filename,
                    "url": f"https://cdn.modrinth.com/data/test/{filename}",
                    "size": len(payload),
                    "primary": True,
                    "hashes": {"sha512": modrinth_client.hashlib.sha512(payload).hexdigest()},
                }
            ],
        }

    def project(self, project_id):
        return self.projects[project_id]

    def version(self, version_id):
        return self.by_version[version_id]

    def latest_version(self, project_id, _game_version, _loader):
        return self.latest.get(project_id)

    def compatible(self, version, game_version, loader):
        return (
            game_version in version["game_versions"]
            and modrinth_client.SUPPORTED_LOADERS[loader] in version["loaders"]
        )

    def open_download(self, url):
        filename = pathlib.PurePosixPath(urllib.parse.urlsplit(url).path).name
        return FakeResponse(self.payloads[filename])


def make_manager(root, client):
    return modrinth_client.ModManager(root, "1.21.1", "Fabric", client=client)


def test_search_filters_version_loader_project_type_and_server_only_results():
    captured = {}

    def opener(request, timeout):
        captured["url"] = request.full_url
        captured["agent"] = request.headers.get("User-agent")
        return FakeResponse(
            json.dumps(
                {
                    "hits": [
                        {"project_id": "client", "environment": ["client_and_server"]},
                        {"project_id": "server", "environment": ["server_only"]},
                        {"project_id": "legacy", "environment": []},
                    ],
                    "total_hits": 3,
                }
            ).encode()
        )

    client = modrinth_client.ModrinthClient(opener=opener)
    result = client.search("sodium", "1.21.1", "Fabric")
    query = urllib.parse.parse_qs(urllib.parse.urlsplit(captured["url"]).query)
    facets = json.loads(query["facets"][0])
    assert ["project_type:mod"] in facets
    assert ["versions:1.21.1"] in facets
    assert ["categories:fabric"] in facets
    assert [f"environment:{value}" for value in modrinth_client.CLIENT_ENVIRONMENTS] in facets
    assert captured["agent"] == modrinth_client.USER_AGENT
    assert [item["project_id"] for item in result["hits"]] == ["client", "legacy"]


def test_github_asset_match_accepts_jar_extension_without_matching_newer_patch():
    assert mod_sources._game_version_in_filename("mod-mc26.2.jar", "26.2")
    assert mod_sources._game_version_in_filename("mod-26.2.jar", "26.2")
    assert not mod_sources._game_version_in_filename("mod-26.2.1.jar", "26.2")

    client = mod_sources.SourceClient()
    client.github_releases = lambda _repo: [
        {
            "id": 123,
            "tag_name": "v1.0.0",
            "name": "Release",
            "draft": False,
            "prerelease": False,
            "assets": [
                {
                    "name": "example-1.0.0-26.2.1.jar",
                    "browser_download_url": "https://github.com/example/wrong.jar",
                    "size": 1,
                },
                {
                    "name": "example-1.0.0-mc26.2.jar",
                    "browser_download_url": "https://github.com/example/correct.jar",
                    "size": 2,
                },
            ],
        }
    ]
    descriptor = client.github_latest(
        "example/project",
        "26.2",
        title="Example",
        source_key="example",
        asset_contains="example",
    )
    assert descriptor["filename"] == "example-1.0.0-mc26.2.jar"


def test_official_essential_sources_track_future_compatible_builds():
    assert mod_sources.ESSENTIAL_SOURCES["trouser-streak"]["repo"] == "etianl/Trouser-Streak"
    assert (
        mod_sources.ESSENTIAL_SOURCES["zazus-server-seeker"]["repo"]
        == "Zazuzin/Zazus-Server-Seeker"
    )
    assert (
        mod_sources.ESSENTIAL_SOURCES["meteor-client"]["repo"] == "MeteorDevelopment/meteor-client"
    )

    client = mod_sources.SourceClient()
    client.github_releases = lambda _repo: [
        {
            "id": 392417310,
            "tag_name": "v1.6.5",
            "draft": False,
            "prerelease": False,
            "assets": [
                {
                    "name": "1trouser-streak-1.6.5-26.2.jar",
                    "browser_download_url": (
                        "https://github.com/etianl/Trouser-Streak/releases/download/"
                        "v1.6.5/1trouser-streak-1.6.5-26.2.jar"
                    ),
                    "size": 874425,
                }
            ],
        }
    ]
    descriptor = client.essential_latest("trouser-streak", "26.2")
    assert descriptor["version_number"] == "v1.6.5"
    assert descriptor["filename"] == "1trouser-streak-1.6.5-26.2.jar"


def test_install_required_dependencies_and_remove_orphans_without_touching_unmanaged_mods():
    with tempfile.TemporaryDirectory() as temporary:
        root = pathlib.Path(temporary) / "instance"
        unmanaged = root / "minecraft" / "mods" / "hand-installed.jar"
        unmanaged.parent.mkdir(parents=True)
        unmanaged.write_bytes(b"leave this alone")
        manager = make_manager(root, FakeClient())
        record = manager.install_project(
            "main", {"project_id": "main", "title": "Main Mod", "slug": "main-mod"}
        )
        assert record["version_id"] == "main-v1"
        assert (manager.mods_dir / "main-v1.jar").read_bytes() == b"main version one"
        assert (manager.mods_dir / "dependency.jar").read_bytes() == b"required dependency"
        assert not (manager.mods_dir / "optional.jar").exists()
        manifest = manager.load_manifest()["mods"]
        assert manifest["main"]["manual"] is True
        assert manifest["dependency"]["manual"] is False
        assert manifest["dependency"]["required_by"] == ["main"]
        assert manager.unmanaged_files() == [unmanaged]

        manager.set_enabled("main", False)
        assert not (manager.mods_dir / "main-v1.jar").exists()
        assert (manager.mods_dir / "main-v1.jar.disabled").is_file()
        manager.set_enabled("main", True)
        assert (manager.mods_dir / "main-v1.jar").is_file()
        assert not (manager.mods_dir / "main-v1.jar.disabled").exists()

        removed = manager.remove_project("main")
        assert removed["kept"] is False
        assert not (manager.mods_dir / "main-v1.jar").exists()
        assert not (manager.mods_dir / "dependency.jar").exists()
        assert unmanaged.read_bytes() == b"leave this alone"


def test_update_replaces_old_file_and_preserves_dependency_tracking():
    with tempfile.TemporaryDirectory() as temporary:
        root = pathlib.Path(temporary) / "instance"
        client = FakeClient()
        manager = make_manager(root, client)
        manager.install_project(
            "main", {"project_id": "main", "title": "Main Mod", "slug": "main-mod"}
        )
        old = manager.load_manifest()["mods"]["main"]
        client.latest["main"] = client.make_version(
            "main",
            "main-v2",
            "2.0.0",
            "main-v2.jar",
            [
                {
                    "project_id": "dependency",
                    "version_id": "dependency-v1",
                    "dependency_type": "required",
                }
            ],
        )
        client.by_version["main-v2"] = client.latest["main"]
        updates = manager.check_updates()
        assert len(updates) == 1
        manager.install_project("main", old, manual=True)
        current = manager.load_manifest()["mods"]
        assert current["main"]["version_id"] == "main-v2"
        assert not (manager.mods_dir / "main-v1.jar").exists()
        assert (manager.mods_dir / "main-v2.jar").read_bytes() == b"main version two"
        assert current["dependency"]["required_by"] == ["main"]


def test_hash_mismatch_never_installs_file():
    with tempfile.TemporaryDirectory() as temporary:
        client = FakeClient()
        client.latest["main"]["files"][0]["hashes"]["sha512"] = "0" * 128
        manager = make_manager(pathlib.Path(temporary) / "instance", client)
        try:
            manager.install_project(
                "main", {"project_id": "main", "title": "Main Mod", "slug": "main-mod"}
            )
        except modrinth_client.ModrinthError as error:
            assert "Hash verification failed" in str(error)
        else:
            raise AssertionError("Hash mismatch was accepted")
        assert not (manager.mods_dir / "main-v1.jar").exists()
        assert not manager.manifest_path.exists()


def test_unmanaged_filename_collision_is_not_overwritten():
    with tempfile.TemporaryDirectory() as temporary:
        root = pathlib.Path(temporary) / "instance"
        collision = root / "minecraft" / "mods" / "main-v1.jar"
        collision.parent.mkdir(parents=True)
        collision.write_bytes(b"user supplied file")
        manager = make_manager(root, FakeClient())
        try:
            manager.install_project(
                "main", {"project_id": "main", "title": "Main Mod", "slug": "main-mod"}
            )
        except modrinth_client.ModrinthError as error:
            assert "unmanaged mod" in str(error)
        else:
            raise AssertionError("Unmanaged mod was overwritten")
        assert collision.read_bytes() == b"user supplied file"


def test_unsafe_filenames_and_vanilla_instances_are_rejected():
    for name in ("../escape.jar", "folder/mod.jar", "folder\\mod.jar", "not-a-jar.zip"):
        try:
            modrinth_client.safe_filename(name)
        except modrinth_client.ModrinthError:
            pass
        else:
            raise AssertionError(f"Unsafe filename accepted: {name}")
    with tempfile.TemporaryDirectory() as temporary:
        try:
            modrinth_client.ModManager(temporary, "1.21.1", "Vanilla", client=FakeClient())
        except modrinth_client.ModrinthError:
            pass
        else:
            raise AssertionError("Vanilla instance accepted by mod manager")


def test_every_jar_in_mods_folder_appears_in_installed_inventory():
    with tempfile.TemporaryDirectory() as temporary:
        root = pathlib.Path(temporary) / "instance"
        mods = root / "minecraft" / "mods"
        mods.mkdir(parents=True)
        (mods / "plain-local.jar").write_bytes(b"not even a readable Fabric archive")
        (mods / "meteor.jar").write_bytes(fabric_jar("meteor-client", "Meteor Client", "old"))
        manager = modrinth_client.ModManager(
            root, "1.21.1", "Fabric", client=FakeClient(), source_client=FakeSourceClient()
        )
        records = manager.installed()
        assert {record["filename"] for record in records} == {"plain-local.jar", "meteor.jar"}
        assert {record["filename"]: record["provider"] for record in records} == {
            "plain-local.jar": "local",
            "meteor.jar": "meteor",
        }


def test_existing_known_mod_records_gain_official_update_sources():
    records = [
        ({"mod_id": "streak-addon", "provider": "local"}, "trouser-streak", "github"),
        (
            {"mod_id": "zazus-server-seeker", "provider": "local"},
            "zazus-server-seeker",
            "github",
        ),
        ({"mod_id": "meteor-client", "provider": "local"}, "meteor-client", "meteor"),
    ]
    for record, source_key, provider in records:
        assert modrinth_client.ModManager._link_known_external_source(record)
        assert record["source_key"] == source_key
        assert record["provider"] == provider
        assert record["repo"] == mod_sources.ESSENTIAL_SOURCES[source_key]["repo"]


def test_unchanged_local_jar_inventory_reuses_cached_identity():
    with tempfile.TemporaryDirectory() as temporary:
        root = pathlib.Path(temporary) / "instance"
        local_path = root / "minecraft" / "mods" / "cached-local.jar"
        local_path.parent.mkdir(parents=True)
        local_path.write_bytes(fabric_jar("cached-local", "Cached Local Mod", "1.0.0"))
        manager = modrinth_client.ModManager(root, "1.21.1", "Fabric", client=FakeClient())

        first = manager.installed()
        assert first[0]["file_size"] == local_path.stat().st_size
        assert first[0]["file_mtime_ns"] == local_path.stat().st_mtime_ns

        with mock.patch.object(
            modrinth_client, "file_hash", side_effect=AssertionError("unexpected rehash")
        ):
            second = manager.installed()
        assert second[0]["sha512"] == first[0]["sha512"]


def test_external_mod_updates_replace_old_file_and_keep_manifest_identity():
    with tempfile.TemporaryDirectory() as temporary:
        root = pathlib.Path(temporary) / "instance"
        source = FakeSourceClient()
        manager = modrinth_client.ModManager(
            root, "1.21.1", "Fabric", client=FakeClient(), source_client=source
        )
        installed = manager.install_external("meteor-client")
        assert installed["record_id"] == "external:meteor-client"
        assert (manager.mods_dir / "meteor-client-1.0.0.jar").is_file()

        source.version = "2.0.0"
        updates = manager.check_updates()
        assert len(updates) == 1
        assert updates[0]["record"]["record_id"] == "external:meteor-client"
        manager.update_record(updates[0]["record"])
        assert not (manager.mods_dir / "meteor-client-1.0.0.jar").exists()
        assert (manager.mods_dir / "meteor-client-2.0.0.jar").is_file()
        current = manager.load_manifest()["mods"]["external:meteor-client"]
        assert current["source_version_id"] == "2.0.0"


def test_hand_added_modrinth_jar_is_identified_by_hash_and_can_update():
    with tempfile.TemporaryDirectory() as temporary:
        root = pathlib.Path(temporary) / "instance"
        client = FakeClient()
        old_payload = fabric_jar("hash-mod", "Hash Identified Mod", "1.0.0")
        client.payloads["hash-mod-v1.jar"] = old_payload
        client.payloads["hash-mod-v2.jar"] = fabric_jar("hash-mod", "Hash Identified Mod", "2.0.0")
        client.projects["hash-project"] = {
            "id": "hash-project",
            "title": "Hash Identified Mod",
            "slug": "hash-identified-mod",
            "icon_url": None,
        }
        installed_version = client.make_version(
            "hash-project", "hash-v1", "1.0.0", "hash-mod-v1.jar", []
        )
        client.latest["hash-project"] = client.make_version(
            "hash-project", "hash-v2", "2.0.0", "hash-mod-v2.jar", []
        )
        client.version_from_hash = lambda digest, algorithm="sha512": installed_version

        local_path = root / "minecraft" / "mods" / "hash-mod-v1.jar"
        local_path.parent.mkdir(parents=True)
        local_path.write_bytes(old_payload)
        manager = modrinth_client.ModManager(
            root, "1.21.1", "Fabric", client=client, source_client=FakeSourceClient()
        )
        updates = manager.check_updates()
        assert len(updates) == 1
        assert updates[0]["record"]["provider"] == "modrinth"
        assert updates[0]["record"]["record_id"] == "hash-project"
        manager.update_record(updates[0]["record"])
        assert not local_path.exists()
        assert (manager.mods_dir / "hash-mod-v2.jar").is_file()


if __name__ == "__main__":
    tests = [value for name, value in sorted(globals().items()) if name.startswith("test_")]
    for test in tests:
        test()
    print(f"Passed {len(tests)} Modrinth support tests")
