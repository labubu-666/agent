from pathlib import Path

from click.testing import CliRunner
from prompt_toolkit.completion import CompleteEvent, Completion
from prompt_toolkit.document import Document

from agent import cli
from agent.skills import Skill


def _write_skill(root: Path, name: str) -> None:
    skill_dir = root / ".claude" / "skills" / name
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        f"---\nname: {name}\ndescription: Does {name}.\n---\n", encoding="utf-8"
    )


def _completions(commands: dict[str, str], text: str) -> list[Completion]:
    completer = cli.SlashCommandCompleter(commands)
    document = Document(text)
    return list(completer.get_completions(document, CompleteEvent()))


def test_completer_suggests_slash_commands_with_descriptions():
    commands = {"/skills": "Lists skills.", "/hello-world": "Greets."}

    completions = _completions(commands, "/he")

    assert [c.text for c in completions] == ["/hello-world"]
    assert completions[0].start_position == -3
    assert completions[0].display_meta_text == "Greets."
    assert [c.text for c in _completions(commands, "/")] == ["/skills", "/hello-world"]


def test_completer_ignores_plain_text_and_skill_arguments():
    commands = {"/hello-world": "Greets."}

    assert _completions(commands, "hello") == []
    assert _completions(commands, "/x") == []
    assert _completions(commands, "/hello-world to Ken") == []


def test_parse_skill_command_returns_name_and_extra_text(tmp_path):
    skill = Skill(
        name="hello-world",
        description="Greets.",
        path=tmp_path / "SKILL.md",
        directory=tmp_path,
    )
    skills = {"hello-world": skill}

    assert cli.parse_skill_command("/hello-world", skills) == ("hello-world", "")
    assert cli.parse_skill_command("/hello-world  to Ken ", skills) == (
        "hello-world",
        "to Ken",
    )
    assert cli.parse_skill_command("/unknown", skills) is None
    assert cli.parse_skill_command("hello-world", skills) is None


def test_format_skills_lists_name_and_description(tmp_path):
    skill = Skill(
        name="pdf",
        description="Works with PDFs.",
        path=tmp_path / "SKILL.md",
        directory=tmp_path,
    )

    assert cli.format_skills({"pdf": skill}) == "- pdf: Works with PDFs."
    assert cli.format_skills({}) == "No skills found."


def test_skills_command_prints_skills_without_calling_agent(tmp_path, monkeypatch):
    home = tmp_path / "home"
    home.mkdir()
    _write_skill(home, "user-skill")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(Path, "home", lambda: home)
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("AGENT_LOG_FILE", str(tmp_path / "agent.jsonl"))
    monkeypatch.setenv("AGENT_SESSIONS_DIR", str(tmp_path / "sessions"))
    monkeypatch.setattr(cli, "configure_logging", lambda log_path: None)

    ran_tasks = []

    class FakeAgent:
        def __init__(self, **kwargs):
            pass

        def run_task(self, task):
            ran_tasks.append(task)

    monkeypatch.setattr(cli, "Agent", FakeAgent)

    result = CliRunner().invoke(cli.main, [], input="/skills\n/exit\n")

    assert result.exit_code == 0, result.output
    assert "- user-skill: Does user-skill." in result.output
    assert ran_tasks == []


def test_skill_command_runs_task_for_that_skill(tmp_path, monkeypatch):
    _write_skill(tmp_path, "hello-world")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(Path, "home", lambda: tmp_path / "no-home")
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("AGENT_LOG_FILE", str(tmp_path / "agent.jsonl"))
    monkeypatch.setenv("AGENT_SESSIONS_DIR", str(tmp_path / "sessions"))
    monkeypatch.setattr(cli, "configure_logging", lambda log_path: None)

    ran_tasks = []

    class FakeAgent:
        def __init__(self, **kwargs):
            pass

        def run_task(self, task):
            ran_tasks.append(task)

    monkeypatch.setattr(cli, "Agent", FakeAgent)

    result = CliRunner().invoke(cli.main, [], input="/hello-world to Ken\n/exit\n")

    assert result.exit_code == 0, result.output
    assert len(ran_tasks) == 1
    assert ran_tasks[0].description == (
        "Run the 'hello-world' skill. Request details: to Ken"
    )
    assert "Does hello-world." in ran_tasks[0].instructions
    assert "Hello, World!" not in result.output
    assert "Does hello-world." not in result.output


def test_working_dir_skills_are_passed_to_agent(tmp_path, monkeypatch):
    project = tmp_path / "project"
    home = tmp_path / "home"
    project.mkdir()
    home.mkdir()
    _write_skill(project, "project-skill")
    _write_skill(home, "user-skill")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(Path, "home", lambda: home)
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("AGENT_LOG_FILE", str(tmp_path / "agent.jsonl"))
    monkeypatch.setenv("AGENT_SESSIONS_DIR", str(tmp_path / "sessions"))
    monkeypatch.setattr(cli, "configure_logging", lambda log_path: None)

    captured = {}

    class FakeAgent:
        def __init__(self, **kwargs):
            captured.update(kwargs)

        def run_task(self, task):
            return None

    monkeypatch.setattr(cli, "Agent", FakeAgent)

    result = CliRunner().invoke(
        cli.main, ["--working-dir", str(project)], input="/exit\n"
    )

    assert result.exit_code == 0, result.output
    skills: dict[str, Skill] = captured["skills"]
    assert list(skills) == ["project-skill", "user-skill"]
    assert (
        skills["project-skill"].directory
        == (project / ".claude" / "skills" / "project-skill").resolve()
    )
