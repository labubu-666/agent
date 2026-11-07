import base64
from types import SimpleNamespace

from agent.agent import Agent, Task
from agent.session import Session

PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32
PNG_URI = "data:image/png;base64," + base64.b64encode(PNG_BYTES).decode("ascii")

FINISH_JSON = '{"action": "finish", "final_answer": "done", "reasoning": "r"}'
READ_IMAGE_JSON = (
    '{"action": "call_tool", "reasoning": "look", '
    '"tool_call": {"tool_name": "read_image", "arguments": {"file_path": "%s"}}}'
)


def _fake_response(content: str):
    message = SimpleNamespace(content=content)
    return SimpleNamespace(choices=[SimpleNamespace(message=message)])


def _image_parts(message):
    content = message["content"]
    if not isinstance(content, list):
        return []
    return [part for part in content if part["type"] == "image_url"]


def test_read_image_result_is_sent_to_model_as_image(tmp_path, monkeypatch):
    image = tmp_path / "pic.png"
    image.write_bytes(PNG_BYTES)
    session = Session.create(root=tmp_path)
    agent = Agent(openai_api_key="test", model="model-x", session=session)
    replies = iter([READ_IMAGE_JSON % image, FINISH_JSON])
    sent = []

    def fake_create(**kwargs):
        sent.append(kwargs["messages"])
        return _fake_response(next(replies))

    monkeypatch.setattr(agent.client.chat.completions, "create", fake_create)

    result = agent.run_task(Task(description="look", max_iterations=3))

    assert result == "done"
    last_user = sent[1][-1]
    assert last_user["role"] == "user"
    assert _image_parts(last_user) == [
        {"type": "image_url", "image_url": {"url": PNG_URI}}
    ]


def test_session_stores_path_not_base64(tmp_path, monkeypatch):
    image = tmp_path / "pic.png"
    image.write_bytes(PNG_BYTES)
    session = Session.create(root=tmp_path)
    agent = Agent(openai_api_key="test", model="model-x", session=session)
    replies = iter([READ_IMAGE_JSON % image, FINISH_JSON])
    monkeypatch.setattr(
        agent.client.chat.completions,
        "create",
        lambda **kwargs: _fake_response(next(replies)),
    )

    agent.run_task(Task(description="look", max_iterations=3))

    raw = session.path.read_text(encoding="utf-8")
    assert str(image.resolve()) in raw
    assert base64.b64encode(PNG_BYTES).decode("ascii") not in raw
    messages = Session.load(session.session_id, root=tmp_path).messages()
    assert [m.role for m in messages] == ["user", "assistant", "user", "assistant"]
    assert messages[2].image_paths == [str(image.resolve())]


def test_resumed_session_rereads_image(tmp_path, monkeypatch):
    image = tmp_path / "pic.png"
    image.write_bytes(PNG_BYTES)
    session = Session.create(root=tmp_path)
    session.append("user", "see this", "model-x", [str(image.resolve())])

    resumed = Session.load(session.session_id, root=tmp_path)
    agent = Agent(openai_api_key="test", model="model-x", session=resumed)
    sent = {}

    def fake_create(**kwargs):
        sent["messages"] = kwargs["messages"]
        return _fake_response(FINISH_JSON)

    monkeypatch.setattr(agent.client.chat.completions, "create", fake_create)
    agent.run_task(Task(description="follow up", max_iterations=2))

    image_urls = [
        part["image_url"]["url"]
        for message in sent["messages"]
        for part in _image_parts(message)
    ]
    assert image_urls == [PNG_URI]


def test_resumed_session_with_deleted_image_sends_note(tmp_path, monkeypatch):
    image = tmp_path / "gone.png"
    session = Session.create(root=tmp_path)
    session.append("user", "see this", "model-x", [str(image.resolve())])

    resumed = Session.load(session.session_id, root=tmp_path)
    agent = Agent(openai_api_key="test", model="model-x", session=resumed)
    sent = {}

    def fake_create(**kwargs):
        sent["messages"] = kwargs["messages"]
        return _fake_response(FINISH_JSON)

    monkeypatch.setattr(agent.client.chat.completions, "create", fake_create)
    agent.run_task(Task(description="follow up", max_iterations=2))

    user_message = sent["messages"][1]
    texts = [part["text"] for part in user_message["content"] if part["type"] == "text"]
    assert any("unavailable" in text and "gone.png" in text for text in texts)
    assert _image_parts(user_message) == []


def test_messages_without_images_stay_plain_strings(tmp_path, monkeypatch):
    session = Session.create(root=tmp_path)
    session.append("user", "plain question", "model-x")
    session.append("assistant", "plain answer", "model-x")

    resumed = Session.load(session.session_id, root=tmp_path)
    agent = Agent(openai_api_key="test", model="model-x", session=resumed)
    sent = {}

    def fake_create(**kwargs):
        sent["messages"] = kwargs["messages"]
        return _fake_response(FINISH_JSON)

    monkeypatch.setattr(agent.client.chat.completions, "create", fake_create)
    agent.run_task(Task(description="next", max_iterations=2))

    assert sent["messages"][1]["content"] == "plain question"
    assert sent["messages"][2]["content"] == "plain answer"


def test_old_session_lines_without_image_paths_still_load(tmp_path):
    session = Session.create(root=tmp_path)
    session.path.write_text(
        '{"role": "user", "content": "old", "model": "m", "timestamp": "2024-01-01T00:00:00+00:00"}\n',
        encoding="utf-8",
    )

    messages = Session.load(session.session_id, root=tmp_path).messages()

    assert messages[0].image_paths == []
