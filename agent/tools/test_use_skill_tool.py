import pytest

from agent.skills import parse_skill_file
from agent.tools.skill import UseSkillTool


@pytest.fixture
def skill(tmp_path):
    skill_dir = tmp_path / "pdf"
    (skill_dir / "scripts").mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        "---\nname: pdf\ndescription: Works with PDFs.\n---\nUse pdftotext.\n",
        encoding="utf-8",
    )
    (skill_dir / "reference.md").write_text("extra", encoding="utf-8")
    (skill_dir / "scripts" / "extract.py").write_text("print(1)", encoding="utf-8")
    return parse_skill_file(skill_dir / "SKILL.md")


def test_use_skill_returns_instructions_and_other_files(skill):
    tool = UseSkillTool({skill.name: skill})

    result = tool.run(skill_name="pdf")

    assert "Skill: pdf" in result
    assert f"Directory: {skill.directory}" in result
    assert "Use pdftotext." in result
    assert "- reference.md" in result
    assert "- scripts/extract.py" in result
    assert "- SKILL.md" not in result


def test_use_skill_reports_unknown_skill_with_available_names(skill):
    tool = UseSkillTool({skill.name: skill})

    result = tool.run(skill_name="missing")

    assert result == "Error: Skill 'missing' not found. Available skills are: ['pdf']"
