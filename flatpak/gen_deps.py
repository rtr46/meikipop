#!/usr/bin/env python3
"""
Generate python3-deps.json for a flatpak build.

Uses pip's resolver to produce a dry-run report of all transitive deps.
Then emits a single-module flatpak manifest that installs the wheels/sdists offline.
Must be run on a flatpak target Linux x86_64 host.
"""

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import tomllib

PROJECT_PATH = Path("pyproject.toml")
OUT_PATH = Path("flatpak/python3-deps.json")

WHEEL_NO_DEPS = ["pynput>=1.8"]
SDIST_PACKAGES = ["evdev"]

PYTHON_VERSION = "3.13"
PLATFORMS = ["manylinux2014_x86_64", "manylinux_2_28_x86_64"]

os.environ["PIP_DISABLE_PIP_VERSION_CHECK"] = "1"


def run_resolve(packages: list[str], extra_args: list[str]) -> list[dict]:
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as tf:
        report_path = Path(tf.name)
    try:
        cmd = [
            sys.executable,
            "-m",
            "pip",
            "install",
            "--dry-run",
            "--ignore-installed",
            "--python-version",
            PYTHON_VERSION,
            "--report",
            str(report_path),
            *extra_args,
            *packages,
        ]
        subprocess.check_call(cmd)
        return json.loads(report_path.read_text())["install"]
    finally:
        report_path.unlink(missing_ok=True)


def main() -> None:
    platform_args = [f"--platform={p}" for p in PLATFORMS]

    deps = [
        dep
        for dep in tomllib.loads(PROJECT_PATH.read_text())["project"]["dependencies"]
        if not dep.startswith("pynput")
    ]
    resolved_packages = [
        *run_resolve(deps, ["--only-binary=:all:", *platform_args]),
        *run_resolve(
            WHEEL_NO_DEPS, ["--only-binary=:all:", "--no-deps", *platform_args]
        ),
        *run_resolve(SDIST_PACKAGES, ["--no-binary=:all:", "--no-deps"]),
    ]

    seen = set()
    sources = []
    for pkg in resolved_packages:
        info = pkg["download_info"]
        url = info["url"]
        if url in seen:
            continue
        seen.add(url)
        sources.append(
            {
                "type": "file",
                "url": url,
                "sha256": info["archive_info"]["hashes"]["sha256"],
            }
        )

    OUT_PATH.write_text(
        json.dumps(
            {
                "name": "python3-deps",
                "buildsystem": "simple",
                "build-commands": [
                    (
                        "pip3 install --no-index --find-links=. --prefix=/app --no-build-isolation --ignore-installed --no-deps *.whl *.tar.gz"
                    )
                ],
                "cleanup": ["/bin", "/share/man"],
                "sources": sources,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
