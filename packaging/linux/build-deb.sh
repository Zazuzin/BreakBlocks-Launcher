#!/usr/bin/env bash
set -euo pipefail

project_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)"
output_dir="$project_root/dist-release"
work_dir="$(mktemp -d)"
trap 'rm -rf -- "$work_dir"' EXIT

package_root="$work_dir/package"
install_root="$package_root/usr/lib/breakblocks-launcher"
app_root="$install_root/app"
debian_root="$package_root/DEBIAN"
mkdir -p "$app_root" "$debian_root" "$package_root/usr/bin"
mkdir -p "$package_root/usr/share/applications"
mkdir -p "$package_root/usr/share/icons/hicolor/256x256/apps"
mkdir -p "$package_root/usr/share/icons/hicolor/64x64/apps"

python3 -m venv "$work_dir/build-env"
build_python="$work_dir/build-env/bin/python"
"$build_python" -m pip install --disable-pip-version-check -r "$project_root/requirements-dev.txt"

cd "$project_root"
"$build_python" -m black --check --line-length 100 ./*.py tests tools
"$build_python" -m ruff check ./*.py tests tools
export PYTHONPATH="$project_root"
for test_file in tests/test_*.py; do
    "$build_python" "$test_file"
done

"$build_python" -m pip install \
    --disable-pip-version-check \
    --no-compile \
    --target "$app_root/vendor" \
    -r "$project_root/requirements.txt"

for file in app_config.py chat_browser.py launcher_update.py minecraft_backend.py \
    mod_sources.py modrinth_client.py process_environment.py zazu_launcher.py; do
    cp "$project_root/$file" "$app_root/$file"
done
cp -R "$project_root/assets" "$app_root/assets"
cp -R "$project_root/fonts" "$install_root/fonts"

for file in LICENSE PRIVACY.md TERMS.md THIRD-PARTY-NOTICES.md; do
    cp "$project_root/$file" "$install_root/$file"
    cp "$project_root/$file" "$app_root/$file"
done
cp "$project_root/packaging/linux/README.txt" "$install_root/README.txt"
printf 'ubuntu-deb\n' > "$install_root/.deb-package"

"$build_python" "$project_root/tools/collect_dependency_licenses.py" \
    --output "$install_root/third-party-licenses"

cp "$project_root/packaging/linux/breakblocks-launcher" "$package_root/usr/bin/"
cp "$project_root/packaging/linux/breakblocks-launcher.desktop" \
    "$package_root/usr/share/applications/"
cp "$project_root/packaging/linux/breakblocks-minecraft.desktop" \
    "$package_root/usr/share/applications/"
cp "$project_root/packaging/linux/breakblocks-launcher.png" \
    "$package_root/usr/share/icons/hicolor/256x256/apps/"
cp "$project_root/packaging/linux/breakblocks-minecraft.png" \
    "$package_root/usr/share/icons/hicolor/64x64/apps/"
cp "$project_root/packaging/linux/control" "$debian_root/control"
cp "$project_root/packaging/linux/postinst" "$debian_root/postinst"
cp "$project_root/packaging/linux/postrm" "$debian_root/postrm"

find "$package_root" -type d -exec chmod 0755 {} +
find "$package_root" -type f -exec chmod 0644 {} +
chmod 0755 "$package_root/usr/bin/breakblocks-launcher" "$debian_root/postinst" "$debian_root/postrm"

mkdir -p "$output_dir"
package="$output_dir/BreakBlocks-Launcher-0.9.11-Ubuntu-amd64.deb"
dpkg-deb --build --root-owner-group "$package_root" "$package"
echo "Created $package"
