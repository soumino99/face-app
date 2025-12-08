"""Utility to normalize face-shape sample images for the dataset.

The script copies the raw crowd-sourced photos under dataset/face-type-photo
into dataset/face-type-photo-standard with the naming convention requested in
Slack (e.g., Oval01.png).

It re-encodes images as PNG to match the expected extension, caps the number of
files per class, and prints a short summary so contributors can tell what is
missing (currently Diamond has no samples).
"""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Dict, Iterable, List

import cv2  # type: ignore

ROOT = Path(__file__).resolve().parents[1]
SOURCE_DIR = ROOT / "dataset" / "face-type-photo"
TARGET_DIR = ROOT / "dataset" / "face-type-photo-standard"
MAX_PER_CLASS = 5
IMG_EXTENSIONS = (".jpg", ".jpeg", ".png")

# Map the crowd-sourced prefixes to the canonical shape labels.
# Multiple prefixes per label are deduplicated in the order listed.
SHAPE_SOURCES: Dict[str, List[str]] = {
    "Oval": ["Egg", "Oval"],
    "Round": ["Round"],
    "Square": ["Base"],
    "Heart": ["Triangle"],
    "Diamond": ["Diamond"],  # no samples yet, will trigger a warning
    "Oblong": ["Rectangle"],
}


def _iter_source_files(prefixes: Iterable[str]) -> List[Path]:
    """Collect candidate files for a shape, keeping natural sort order."""
    files: List[Path] = []
    seen = set()
    for prefix in prefixes:
        for suffix in IMG_EXTENSIONS:
            for path in sorted(SOURCE_DIR.glob(f"{prefix}*{suffix}")):
                if path in seen:
                    continue
                files.append(path)
                seen.add(path)
    return files


def _convert_to_png(src: Path, dst: Path) -> None:
    image = cv2.imread(src.as_posix())
    if image is None:
        raise RuntimeError(f"Failed to read image: {src}")
    ok = cv2.imwrite(dst.as_posix(), image)
    if not ok:
        raise RuntimeError(f"Failed to write image: {dst}")


def main() -> None:
    if not SOURCE_DIR.exists():
        raise SystemExit(f"Source directory not found: {SOURCE_DIR}")

    if TARGET_DIR.exists():
        shutil.rmtree(TARGET_DIR)
    TARGET_DIR.mkdir(parents=True)

    print(f"Preparing normalized dataset at {TARGET_DIR}")
    for label, prefixes in SHAPE_SOURCES.items():
        candidates = _iter_source_files(prefixes)
        if not candidates:
            print(f"[WARN] No source images found for '{label}' (prefixes={prefixes}).")
            continue

        limit = min(MAX_PER_CLASS, len(candidates))
        for idx in range(limit):
            src = candidates[idx]
            dst = TARGET_DIR / f"{label}{idx + 1:02d}.png"
            _convert_to_png(src, dst)
        print(f"[OK] {label}: wrote {limit} file(s) from prefixes {prefixes}.")

    print("Done. Please drop new images into the raw folder and re-run as needed.")


if __name__ == "__main__":
    main()
