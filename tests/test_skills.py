"""Validate SKILL.md files against the Agent Skills format and the server's tools."""

from __future__ import annotations

import re
import zipfile
from pathlib import Path

import pytest

import package_skills
from tests.test_server import EXPECTED_TOOLS  # the protocol test asserts the server exposes exactly these

SKILL_DIRS = sorted(p for p in package_skills.SKILLS_DIR.iterdir() if p.is_dir())


def frontmatter(skill_dir: Path) -> tuple[dict[str, str], str]:
    text = (skill_dir / "SKILL.md").read_text(encoding="utf-8")
    m = re.match(r"^---\n(.*?)\n---\n(.*)$", text, re.DOTALL)
    assert m, "SKILL.md must start with YAML frontmatter between --- lines"
    fields = dict(line.split(":", 1) for line in m[1].splitlines() if ":" in line)
    return {k.strip(): v.strip() for k, v in fields.items()}, m[2]


def test_expected_skills_exist() -> None:
    assert [p.name for p in SKILL_DIRS] == ["customer-email-draft", "weekly-sales-summary"]


@pytest.mark.parametrize("skill_dir", SKILL_DIRS, ids=lambda p: p.name)
def test_frontmatter_follows_spec(skill_dir: Path) -> None:
    fields, body = frontmatter(skill_dir)
    name, description = fields["name"], fields["description"]
    assert name == skill_dir.name
    assert re.fullmatch(r"[a-z0-9-]{1,64}", name)
    assert "anthropic" not in name and "claude" not in name
    assert 0 < len(description) <= 1024 and "<" not in description
    assert "Use when" in description  # says *when* to trigger, not only what it does
    assert len(body.split()) < 1500  # stays well under the ~5k token guidance


@pytest.mark.parametrize("skill_dir", SKILL_DIRS, ids=lambda p: p.name)
def test_referenced_tools_exist(skill_dir: Path) -> None:
    text = (skill_dir / "SKILL.md").read_text(encoding="utf-8")
    referenced = set(re.findall(r"`(get_[a-z_]+|list_[a-z_]+)`", text))
    assert referenced, "skill should name the tools it uses"
    assert referenced <= EXPECTED_TOOLS


def test_email_skill_never_sends() -> None:
    text = (package_skills.SKILLS_DIR / "customer-email-draft" / "SKILL.md").read_text(encoding="utf-8")
    assert "Never send email" in text and "DRAFT" in text


def test_package_creates_zip_with_skill_folder(tmp_path: Path) -> None:
    target = package_skills.package_skill(SKILL_DIRS[0], tmp_path)
    with zipfile.ZipFile(target) as zf:
        assert f"{SKILL_DIRS[0].name}/SKILL.md" in zf.namelist()
