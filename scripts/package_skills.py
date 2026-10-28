"""Zip each folder in skills/ for upload to Claude (Settings > Features > Skills).

Usage:
    python scripts/package_skills.py        # writes dist/skills/<name>.zip
"""

from __future__ import annotations

import zipfile
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SKILLS_DIR = PROJECT_ROOT / "skills"
OUT_DIR = PROJECT_ROOT / "dist" / "skills"


def package_skill(skill_dir: Path, out_dir: Path = OUT_DIR) -> Path:
    """Create ``<name>.zip`` containing the skill folder (``<name>/SKILL.md`` ...)."""
    if not (skill_dir / "SKILL.md").exists():
        raise FileNotFoundError(f"{skill_dir} has no SKILL.md")
    out_dir.mkdir(parents=True, exist_ok=True)
    target = out_dir / f"{skill_dir.name}.zip"
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as zf:
        for path in sorted(skill_dir.rglob("*")):
            if path.is_file():
                zf.write(path, path.relative_to(skill_dir.parent).as_posix())
    return target


def main() -> None:
    for skill_dir in sorted(p for p in SKILLS_DIR.iterdir() if p.is_dir()):
        print(f"Packaged {package_skill(skill_dir)}")


if __name__ == "__main__":
    main()
