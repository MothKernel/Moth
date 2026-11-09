#!/usr/bin/env bash
set -euo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.."
if [[ "$(uname -s)" != Darwin ]]; then
  echo 'Build this DMG on macOS after running PyInstaller.' >&2
  exit 1
fi
version="$(python3 -c 'import tomllib; print(tomllib.load(open("pyproject.toml", "rb"))["project"]["version"])')"
arch="$(uname -m)"
[[ "$arch" == arm64 || "$arch" == x86_64 ]]
[[ -d dist/Moth.app ]]
mkdir -p release
stage="$(mktemp -d "${TMPDIR:-/tmp}/moth-dmg.XXXXXX")"
trap 'rm -rf -- "$stage"' EXIT
ditto dist/Moth.app "$stage/Moth.app"
ln -s /Applications "$stage/Applications"
output="release/Moth-${version}-macOS-${arch}.dmg"
hdiutil create -volname Moth -srcfolder "$stage" -format UDZO -ov "$output"
(cd release && shasum -a 256 "$(basename "$output")") > "${output}.sha256"
