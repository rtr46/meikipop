#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_root"

venv_dir="$repo_root/venv"
python_cmd="$venv_dir/bin/python"

if [[ ! -x "$python_cmd" ]]; then
  python3 -m venv "$venv_dir"
fi

"$python_cmd" -m pip install -U pip
"$python_cmd" -m pip install -r requirements.txt
"$python_cmd" -m pip install pyinstaller lxml

if [[ ! -f "jmdict_enhanced.pkl" ]]; then
  "$python_cmd" -m scripts.build_dictionary
fi

rm -rf dist build
pyinstaller_config_dir="$(mktemp -d "${TMPDIR:-/tmp}/meikipop-pyinstaller.XXXXXX")"
trap 'rm -rf "$pyinstaller_config_dir"' EXIT
export PYINSTALLER_CONFIG_DIR="$pyinstaller_config_dir"
"$python_cmd" -m PyInstaller meikipop.macos.spec

echo "Built: $repo_root/dist/meikipop.app"
