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
pyinstaller --clean meikipop.macos.spec

echo "Built: $repo_root/dist/meikipop.app"
