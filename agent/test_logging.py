import json
import logging

import pytest
import structlog

from agent import cli


@pytest.fixture
def restore_logging(tmp_path):
    """Points the log file at tmp_path and restores global logging state afterwards."""
    log_file = tmp_path / "agent.jsonl"

    root = logging.getLogger()
    original_handlers = list(root.handlers)
    original_level = root.level
    yield log_file

    for handler in root.handlers:
        if handler not in original_handlers:
            handler.close()
    root.handlers[:] = original_handlers
    root.setLevel(original_level)
    structlog.reset_defaults()


def test_configure_logging_writes_jsonl_file(restore_logging):
    log_file = restore_logging

    cli.configure_logging(log_file)
    structlog.get_logger("tests").info("structlog event", task="demo")
    logging.getLogger("httpx2").debug("stdlib debug event")

    for handler in logging.getLogger().handlers:
        handler.flush()

    records = [
        json.loads(line) for line in log_file.read_text(encoding="utf-8").splitlines()
    ]

    assert any(r.get("event") == "structlog event" for r in records)
    assert any(r.get("event") == "stdlib debug event" for r in records)
    for record in records:
        assert "level" in record
        assert "timestamp" in record


def test_console_only_shows_warnings_and_above(restore_logging, capsys):
    cli.configure_logging(restore_logging)
    logger = structlog.get_logger("tests")

    logger.info("quiet info")
    logger.warning("loud warning")

    for handler in logging.getLogger().handlers:
        handler.flush()

    captured = capsys.readouterr()
    assert "quiet info" not in captured.err
    assert "loud warning" in captured.err
    assert "quiet info" not in captured.out
    assert "loud warning" not in captured.out
