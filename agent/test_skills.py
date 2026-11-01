from pathlib import Path

import pytest

from agent.skills import default_skill_dirs, discover_skills, parse_skill_file


def _write_skill(root: Path, folder: str, content: str) -> Path:
    skill_dir = root / folder
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(content, encoding="utf-8")
    return skill_dir


def test_parse_skill_file_reads_name_and_description(tmp_path):
    skill_dir = _write_skill(
        tmp_path,
        "pdf",
        "---\nname: pdf-tools\ndescription: Works with PDF files.\n---\n# Body\n",
    )

    skill = parse_skill_file(skill_dir / "SKILL.md")

    assert skill.name == "pdf-tools"
    assert skill.description == "Works with PDF files."
    assert skill.path == (skill_dir / "SKILL.md").resolve()
    assert skill.directory == skill_dir.resolve()
    assert skill.metadata == {}


def test_parse_skill_file_supports_multiline_description(tmp_path):
    skill_dir = _write_skill(
        tmp_path,
        "notes",
        "---\nname: notes\ndescription: >\n  Takes notes:\n  and summarizes them.\n---\n",
    )

    skill = parse_skill_file(skill_dir / "SKILL.md")

    assert skill.description == "Takes notes: and summarizes them."


def test_parse_skill_file_keeps_extra_front_matter_fields(tmp_path):
    skill_dir = _write_skill(
        tmp_path,
        "reader",
        "---\nname: reader\ndescription: Reads.\nallowed-tools: Read, Grep\n---\n",
    )

    skill = parse_skill_file(skill_dir / "SKILL.md")

    assert skill.metadata == {"allowed-tools": "Read, Grep"}


@pytest.mark.parametrize(
    "content, message",
    [
        ("# no front matter\n", "must start with a '---'"),
        ("---\nname: a\ndescription: b\n", "missing its closing '---'"),
        ("---\n- just\n- a list\n---\n", "must be a YAML mapping"),
        ("---\ndescription: b\n---\n", "missing a 'name'"),
        ("---\nname: a\n---\n", "missing a 'description'"),
        ("---\nname: Bad Name\ndescription: b\n---\n", "Invalid skill name"),
        ("---\nname: " + "a" * 65 + "\ndescription: b\n---\n", "Invalid skill name"),
        ("---\nname: a\ndescription: " + "x" * 1025 + "\n---\n", "longer than 1024"),
    ],
)
def test_invalid_skill_files_are_rejected(tmp_path, content, message):
    skill_dir = _write_skill(tmp_path, "bad", content)

    with pytest.raises(ValueError, match=message):
        parse_skill_file(skill_dir / "SKILL.md")


def test_discover_skills_returns_valid_skills_sorted_by_name(tmp_path):
    _write_skill(tmp_path, "b", "---\nname: beta\ndescription: B.\n---\n")
    _write_skill(tmp_path, "a", "---\nname: alpha\ndescription: A.\n---\n")

    skills = discover_skills([tmp_path])

    assert list(skills) == ["alpha", "beta"]


def test_discover_skills_skips_invalid_skills_and_missing_dirs(tmp_path):
    _write_skill(tmp_path, "bad", "not a skill")
    _write_skill(tmp_path, "good", "---\nname: good\ndescription: Fine.\n---\n")

    skills = discover_skills([tmp_path / "missing", tmp_path])

    assert list(skills) == ["good"]


def test_earlier_directory_wins_on_duplicate_name(tmp_path):
    project = tmp_path / "project"
    user = tmp_path / "user"
    _write_skill(project, "x", "---\nname: shared\ndescription: Project.\n---\n")
    _write_skill(user, "x", "---\nname: shared\ndescription: User.\n---\n")

    skills = discover_skills([project, user])

    assert skills["shared"].description == "Project."


def test_default_skill_dirs_are_project_then_user(monkeypatch, tmp_path):
    monkeypatch.setattr(Path, "home", lambda: tmp_path)

    assert default_skill_dirs() == [
        Path(".claude") / "skills",
        tmp_path / ".claude" / "skills",
    ]
