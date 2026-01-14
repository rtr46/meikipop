#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_root"

python -m pip install -r requirements.txt
python -m pip install pyinstaller lxml

if [[ ! -f "jmdict_enhanced.pkl" ]]; then
  python -m scripts.build_dictionary
fi

rm -rf dist build
pyinstaller_config_dir="$(mktemp -d "${TMPDIR:-/tmp}/meikipop-pyinstaller.XXXXXX")"
trap 'rm -rf "$pyinstaller_config_dir"' EXIT
export PYINSTALLER_CONFIG_DIR="$pyinstaller_config_dir"
pyinstaller meikipop.macos.spec

echo "Built: $repo_root/dist/meikipop.app"
