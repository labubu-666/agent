from agent import cli


def _shown(text) -> str:
    return "".join(fragment[1] for fragment in text)


def test_status_bar_shows_model_context_percentage_and_cost():
    shown = _shown(cli.status_bar_text("model-a", 32_000, 128_000, 0.0123))

    assert "model-a" in shown
    assert "25% " in shown
    assert "$0.0123" in shown


def test_status_bar_percentage_is_capped_at_100():
    shown = _shown(cli.status_bar_text("model-a", 200_000, 128_000, 0))

    assert "100% " in shown


def test_status_bar_shows_question_mark_when_window_is_unknown():
    shown = _shown(cli.status_bar_text("model-a", 500, 0, 0))

    assert "Context: ? " in shown


def test_status_bar_text_is_styled():
    styles = {fragment[0] for fragment in cli.status_bar_text("model-a", 0, 1, 0)}

    assert styles == {"class:bottom-toolbar.label", "class:bottom-toolbar.value"}
