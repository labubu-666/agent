import json
import uuid

import pytest

from agent.session import Session, uuid7


def test_uuid7_is_version_7_and_rfc_variant():
    value = uuid7()

    assert value.version == 7
    assert value.variant == uuid.RFC_4122


def test_uuid7_timestamp_bits_are_non_decreasing():
    first = uuid7()
    second = uuid7()

    assert (first.int >> 80) <= (second.int >> 80)


def test_create_makes_session_file_with_uuid7_id(tmp_path):
    session = Session.create(root=tmp_path)

    assert uuid.UUID(session.session_id).version == 7
    assert session.path == tmp_path / f"{session.session_id}.jsonl"
    assert session.path.exists()
    assert session.messages() == []


def test_append_and_reload_round_trip_with_model(tmp_path):
    session = Session.create(root=tmp_path)
    session.append("user", "hello", "model-a")
    session.append("assistant", "hi there", "model-a")

    messages = Session.load(session.session_id, root=tmp_path).messages()

    assert [(m.role, m.content, m.model) for m in messages] == [
        ("user", "hello", "model-a"),
        ("assistant", "hi there", "model-a"),
    ]
    assert all(m.timestamp for m in messages)


def test_each_line_is_json_with_model(tmp_path):
    session = Session.create(root=tmp_path)
    session.append("user", "prompt", "model-b")

    record = json.loads(session.path.read_text(encoding="utf-8").splitlines()[0])

    assert record["role"] == "user"
    assert record["content"] == "prompt"
    assert record["model"] == "model-b"


def test_error_entries_round_trip(tmp_path):
    session = Session.create(root=tmp_path)
    session.append("error", "APIError: boom", "model-c")

    messages = Session.load(session.session_id, root=tmp_path).messages()

    assert [(m.role, m.content, m.model) for m in messages] == [
        ("error", "APIError: boom", "model-c"),
    ]


def test_load_unknown_session_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        Session.load(str(uuid7()), root=tmp_path)


def test_load_invalid_id_raises(tmp_path):
    with pytest.raises(ValueError):
        Session.load("not-a-uuid", root=tmp_path)
