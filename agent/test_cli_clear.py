from pathlib import Path

from click.testing import CliRunner
from prompt_toolkit.completion import CompleteEvent
from prompt_toolkit.document import Document

from agent import cli
from agent.agent import Agent
from agent.session import Session


def test_clear_context_empties_chat_history_but_keeps_session_file(tmp_path):
    session = Session.create(root=tmp_path)
    session.append("user", "hello", "model-a")
    session.append("assistant", "hi there", "model-a")
    agent = Agent(openai_api_key="test-key", model="model-a", session=session)
    assert len(agent.chat_history) == 2

    agent.clear_context()

    assert agent.chat_history == []
    assert [m.content for m in session.messages()] == ["hello", "hi there"]


def test_clear_command_clears_context_without_running_task(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(Path, "home", lambda: tmp_path / "no-home")
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("AGENT_LOG_FILE", str(tmp_path / "agent.jsonl"))
    monkeypatch.setenv("AGENT_SESSIONS_DIR", str(tmp_path / "sessions"))
    monkeypatch.setattr(cli, "configure_logging", lambda log_path: None)

    events = []

    class FakeAgent:
        def __init__(self, **kwargs):
            pass

        def run_task(self, task):
            events.append(("task", task.description))

        def clear_context(self):
            events.append(("clear", None))

    monkeypatch.setattr(cli, "Agent", FakeAgent)

    result = CliRunner().invoke(cli.main, [], input="/clear\n/exit\n")

    assert result.exit_code == 0, result.output
    assert events == [("clear", None)]
    assert "Context cleared." in result.output


def test_clear_command_clears_screen_and_pending_attachments(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(Path, "home", lambda: tmp_path / "no-home")
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("AGENT_LOG_FILE", str(tmp_path / "agent.jsonl"))
    monkeypatch.setenv("AGENT_SESSIONS_DIR", str(tmp_path / "sessions"))
    monkeypatch.setattr(cli, "configure_logging", lambda log_path: None)
    monkeypatch.setattr(
        cli,
        "make_prompt",
        lambda commands, attachments, attachment_dir: _prompt_adding_image(
            attachments, tmp_path
        ),
    )

    screen_clears = []
    monkeypatch.setattr(cli.click, "clear", lambda: screen_clears.append(True))

    tasks = []

    class FakeAgent:
        def __init__(self, **kwargs):
            pass

        def run_task(self, task):
            tasks.append(task)

        def clear_context(self):
            pass

    monkeypatch.setattr(cli, "Agent", FakeAgent)

    result = CliRunner().invoke(cli.main, [])

    assert result.exit_code == 0, result.output
    assert screen_clears == [True]
    assert len(tasks) == 1
    assert tasks[0].image_paths == []


def _prompt_adding_image(attachments, tmp_path):
    """Returns a prompt reader that attaches one image before the first input."""
    lines = iter(["/clear", "hello", "/exit"])
    first = [True]

    def read_input():
        if first[0]:
            first[0] = False
            attachments.append(tmp_path / "pending.png")
        return next(lines)

    return read_input


def test_clear_command_is_offered_in_completions():
    commands = {cli.CLEAR_COMMAND: "Clear the conversation context."}
    completer = cli.SlashCommandCompleter(commands)

    completions = list(completer.get_completions(Document("/cl"), CompleteEvent()))

    assert [c.text for c in completions] == ["/clear"]
