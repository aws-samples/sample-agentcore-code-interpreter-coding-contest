#!/usr/bin/env python3
"""Build script to prepare deployment sources from contents/ directory.

Produces two output directories:
- build/problems/  : test_solver.py + metadata.json per problem (-> Problems Bucket)
- build/assets/    : image assets per problem (-> Web Bucket)
"""

import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CONTENTS = ROOT / "contents"
BUILD = ROOT / "build"
PROBLEMS_OUT = BUILD / "problems"
ASSETS_OUT = BUILD / "assets"

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".svg", ".webp"}


def clean():
    if BUILD.exists():
        shutil.rmtree(BUILD)


def build():
    clean()
    PROBLEMS_OUT.mkdir(parents=True)
    ASSETS_OUT.mkdir(parents=True)

    problem_dirs = sorted(d for d in CONTENTS.iterdir() if d.is_dir())
    if not problem_dirs:
        print("No problem directories found in contents/", file=sys.stderr)
        sys.exit(1)

    for problem_dir in problem_dirs:
        pid = problem_dir.name
        metadata_file = problem_dir / "metadata.json"
        test_file = problem_dir / "test_solver.py"

        if not metadata_file.exists():
            print(f"WARNING: {pid}/ missing metadata.json, skipping", file=sys.stderr)
            continue

        # Validate metadata
        with open(metadata_file) as f:
            metadata = json.load(f)
        for field in ("title", "order", "enabled"):
            if field not in metadata:
                print(f"ERROR: {pid}/metadata.json missing required field '{field}'", file=sys.stderr)
                sys.exit(1)

        if not test_file.exists():
            print(f"WARNING: {pid}/ missing test_solver.py, skipping", file=sys.stderr)
            continue

        # Copy to problems output
        dest = PROBLEMS_OUT / pid
        dest.mkdir()
        shutil.copy2(test_file, dest / "test_solver.py")
        shutil.copy2(metadata_file, dest / "metadata.json")

        # Copy assets to web output
        assets_dir = problem_dir / "assets"
        if assets_dir.exists():
            dest_assets = ASSETS_OUT / pid / "assets"
            dest_assets.mkdir(parents=True)
            for f in assets_dir.iterdir():
                if f.is_file() and f.suffix.lower() in IMAGE_EXTENSIONS:
                    shutil.copy2(f, dest_assets / f.name)

    print(f"Build complete: {PROBLEMS_OUT} / {ASSETS_OUT}")


if __name__ == "__main__":
    build()
