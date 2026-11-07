import json
from types import SimpleNamespace

from agent.agent import Agent, Task
from agent.session import Session
from agent.skills import Skill


def _fake_response(content: str):
    message = SimpleNamespace(content=content)
    return SimpleNamespace(choices=[SimpleNamespace(message=message)])


FINISH_JSON = '{"action": "finish", "final_answer": "done", "reasoning": "r"}'


def test_agent_persists_prompts_and_replies_with_model(tmp_path, monkeypatch):
    session = Session.create(root=tmp_path)
    agent = Agent(openai_api_key="test", model="model-x", session=session)
    monkeypatch.setattr(
        agent.client.chat.completions,
        "create",
        lambda **kwargs: _fake_response(FINISH_JSON),
    )

    agent.run_task(Task(description="do it", max_iterations=3))

    messages = Session.load(session.session_id, root=tmp_path).messages()
    assert [(m.role, m.model) for m in messages] == [
        ("user", "model-x"),
        ("assistant", "model-x"),
    ]
    assert "do it" in messages[0].content


def test_resumed_agent_sends_saved_history(tmp_path, monkeypatch):
    session = Session.create(root=tmp_path)
    session.append("user", "earlier question", "model-x")
    session.append("assistant", "earlier answer", "model-x")

    resumed = Session.load(session.session_id, root=tmp_path)
    agent = Agent(openai_api_key="test", model="model-x", session=resumed)

    sent = {}

    def fake_create(**kwargs):
        sent["messages"] = kwargs["messages"]
        return _fake_response(FINISH_JSON)

    monkeypatch.setattr(agent.client.chat.completions, "create", fake_create)

    agent.run_task(Task(description="follow up", max_iterations=2))

    contents = [m["content"] for m in sent["messages"]]
    assert sent["messages"][0]["role"] == "system"
    assert "earlier question" in contents
    assert "earlier answer" in contents
    assert contents[-1].endswith("follow up")


def test_llm_failure_is_recorded_as_error(tmp_path, monkeypatch):
    session = Session.create(root=tmp_path)
    agent = Agent(openai_api_key="test", model="model-x", session=session)

    def failing_create(**kwargs):
        raise RuntimeError("connection refused")

    monkeypatch.setattr(agent.client.chat.completions, "create", failing_create)

    agent.run_task(Task(description="do it", max_iterations=3))

    messages = Session.load(session.session_id, root=tmp_path).messages()
    assert [m.role for m in messages] == ["user", "error"]
    assert messages[1].content == "RuntimeError: connection refused"
    assert messages[1].model == "model-x"


def test_unparseable_reply_is_recorded_and_model_is_asked_to_retry(
    tmp_path, monkeypatch
):
    session = Session.create(root=tmp_path)
    agent = Agent(openai_api_key="test", model="model-x", session=session)
    replies = iter(["not json at all", FINISH_JSON])
    sent = []

    def fake_create(**kwargs):
        sent.append(kwargs["messages"])
        return _fake_response(next(replies))

    monkeypatch.setattr(agent.client.chat.completions, "create", fake_create)

    result = agent.run_task(Task(description="do it", max_iterations=3))

    assert result == "done"
    messages = Session.load(session.session_id, root=tmp_path).messages()
    assert [m.role for m in messages] == [
        "user",
        "assistant",
        "error",
        "user",
        "assistant",
    ]
    assert messages[1].content == "not json at all"
    correction = sent[1][-1]["content"]
    assert correction.startswith("Your last reply was not valid.")


def test_xml_tool_call_reply_is_accepted(tmp_path, monkeypatch):
    session = Session.create(root=tmp_path)
    agent = Agent(openai_api_key="test", model="model-x", session=session)
    xml_reply = (
        "\n<reasoning>Need the file.</reasoning>\n"
        "<tool_call>\n"
        '{"tool_name": "read_file", "arguments": {"file_path": "a.txt"}}\n'
        "</tool_call>"
    )
    replies = iter([xml_reply, FINISH_JSON])
    monkeypatch.setattr(
        agent.client.chat.completions,
        "create",
        lambda **kwargs: _fake_response(next(replies)),
    )
    called = {}

    def fake_run(**kwargs):
        called.update(kwargs)
        return "contents"

    monkeypatch.setattr(agent.tools["read_file"], "run", fake_run)

    result = agent.run_task(Task(description="read it", max_iterations=3))

    assert result == "done"
    assert called["file_path"] == "a.txt"
    messages = Session.load(session.session_id, root=tmp_path).messages()
    assert [m.role for m in messages] == ["user", "assistant", "user", "assistant"]


def test_xml_reply_without_reasoning_still_parses():
    action = Agent._parse_action(
        '<tool_call>{"tool_name": "read_file", "arguments": {}}</tool_call>'
    )

    assert action.action == "call_tool"
    assert action.tool_call is not None
    assert action.tool_call.tool_name == "read_file"
    assert action.reasoning == ""


def test_json_after_prose_with_braces_is_parsed(tmp_path, monkeypatch):
    session = Session.create(root=tmp_path)
    agent = Agent(openai_api_key="test", model="model-x", session=session)
    monkeypatch.setattr(
        agent.client.chat.completions,
        "create",
        lambda **kwargs: _fake_response(f"Looking up {{pk}} first. {FINISH_JSON}"),
    )

    result = agent.run_task(Task(description="do it", max_iterations=3))

    assert result == "done"
    messages = Session.load(session.session_id, root=tmp_path).messages()
    assert [m.role for m in messages] == ["user", "assistant"]


def test_finish_without_reasoning_is_accepted(tmp_path, monkeypatch):
    session = Session.create(root=tmp_path)
    agent = Agent(openai_api_key="test", model="model-x", session=session)
    monkeypatch.setattr(
        agent.client.chat.completions,
        "create",
        lambda **kwargs: _fake_response('{"action": "finish", "final_answer": "done"}'),
    )

    result = agent.run_task(Task(description="do it", max_iterations=3))

    assert result == "done"
    messages = Session.load(session.session_id, root=tmp_path).messages()
    assert [m.role for m in messages] == ["user", "assistant"]


def test_error_entries_are_not_sent_on_resume(tmp_path, monkeypatch):
    session = Session.create(root=tmp_path)
    session.append("user", "first try", "model-x")
    session.append("error", "RuntimeError: connection refused", "model-x")

    resumed = Session.load(session.session_id, root=tmp_path)
    agent = Agent(openai_api_key="test", model="model-x", session=resumed)

    sent = {}

    def fake_create(**kwargs):
        sent["messages"] = kwargs["messages"]
        return _fake_response(FINISH_JSON)

    monkeypatch.setattr(agent.client.chat.completions, "create", fake_create)

    agent.run_task(Task(description="retry", max_iterations=2))

    contents = [m["content"] for m in sent["messages"]]
    assert "RuntimeError: connection refused" not in contents
    assert "first try" in contents


def test_system_prompt_lists_skills_and_offers_use_skill(tmp_path):
    skill = Skill(
        name="pdf",
        description="Works with PDFs.",
        path=tmp_path / "SKILL.md",
        directory=tmp_path,
    )
    agent = Agent(
        openai_api_key="test",
        model="model-x",
        session=Session.create(root=tmp_path),
        skills={"pdf": skill},
    )

    prompt = agent._build_system_prompt()

    assert "- pdf: Works with PDFs." in prompt
    assert "use_skill" in agent.tools


def test_system_prompt_has_no_skills_without_skills(tmp_path):
    agent = Agent(
        openai_api_key="test",
        model="model-x",
        session=Session.create(root=tmp_path),
    )

    prompt = agent._build_system_prompt()

    assert "Available skills" not in prompt
    assert "use_skill" not in agent.tools


def test_agent_uses_openai_base_url_env_when_not_given(monkeypatch):
    monkeypatch.setenv("OPENAI_BASE_URL", "http://localhost:9999/v1")

    agent = Agent(openai_api_key="test", model="model-x", session=None)

    assert str(agent.client.base_url).rstrip("/") == "http://localhost:9999/v1"


def test_system_prompt_includes_startup_instructions(tmp_path, monkeypatch):
    repo = tmp_path / "repo"
    (repo / ".git").mkdir(parents=True)
    (repo / "AGENTS.md").write_text("Use tabs.\n")
    monkeypatch.chdir(repo)
    agent = Agent(
        openai_api_key="test",
        model="model-x",
        session=Session.create(root=tmp_path),
        working_dir=repo,
        home_dir=tmp_path / "home",
    )
    sent = {}

    def fake_create(**kwargs):
        sent["system"] = kwargs["messages"][0]["content"]
        return _fake_response(FINISH_JSON)

    monkeypatch.setattr(agent.client.chat.completions, "create", fake_create)

    agent.run_task(Task(description="do it", max_iterations=2))

    assert "Project instructions" in sent["system"]
    assert "Use tabs." in sent["system"]


def test_startup_instructions_are_reread_on_each_task(tmp_path, monkeypatch):
    repo = tmp_path / "repo"
    (repo / ".git").mkdir(parents=True)
    agents_file = repo / "AGENTS.md"
    agents_file.write_text("first version\n")
    agent = Agent(
        openai_api_key="test",
        model="model-x",
        session=Session.create(root=tmp_path),
        working_dir=repo,
        home_dir=tmp_path / "home",
    )
    sent = []

    def fake_create(**kwargs):
        sent.append(kwargs["messages"][0]["content"])
        return _fake_response(FINISH_JSON)

    monkeypatch.setattr(agent.client.chat.completions, "create", fake_create)

    agent.run_task(Task(description="one", max_iterations=2))
    agents_file.write_text("second version\n")
    agent.run_task(Task(description="two", max_iterations=2))

    assert "first version" in sent[0]
    assert "second version" in sent[1]


def test_reading_subfolder_file_adds_its_instructions_once(tmp_path, monkeypatch):
    repo = tmp_path / "repo"
    (repo / ".git").mkdir(parents=True)
    (repo / "sub").mkdir()
    (repo / "sub" / "notes.txt").write_text("hello\n")
    (repo / "sub" / "AGENTS.md").write_text("sub rules\n")
    agent = Agent(
        openai_api_key="test",
        model="model-x",
        session=Session.create(root=tmp_path),
        working_dir=repo,
        home_dir=tmp_path / "home",
    )
    read_call = json.dumps(
        {
            "action": "call_tool",
            "reasoning": "r",
            "tool_call": {
                "tool_name": "read_file",
                "arguments": {"file_path": str(repo / "sub" / "notes.txt")},
            },
        }
    )
    replies = iter([read_call, read_call, FINISH_JSON])
    sent = []

    def fake_create(**kwargs):
        sent.append(kwargs["messages"])
        return _fake_response(next(replies))

    monkeypatch.setattr(agent.client.chat.completions, "create", fake_create)

    agent.run_task(Task(description="read it", max_iterations=5))

    user_texts = [m["content"] for m in sent[-1] if m["role"] == "user"]
    observations = [t for t in user_texts if "Observation" in t]
    assert len(observations) == 2
    assert sum("sub rules" in o for o in observations) == 1
