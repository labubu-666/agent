import logging
import os
import sys
from collections.abc import Callable, Iterable
from pathlib import Path
from typing import Any

import click
import structlog
from prompt_toolkit import PromptSession
from prompt_toolkit.completion import CompleteEvent, Completer, Completion
from prompt_toolkit.document import Document
from pydantic import ValidationError

from .agent import Agent, Task
from .session import Session
from .settings import Settings
from .skills import Skill, default_skill_dirs, discover_skills

logger = structlog.get_logger(__name__)

EXIT_COMMANDS = {"/exit", "/quit"}
SKILLS_COMMAND = "/skills"


def parse_skill_command(
    description: str, skills: dict[str, Skill]
) -> tuple[str, str] | None:
    """Returns (skill name, extra text) if the input is '/<skill name> [text]'."""
    if not description.startswith("/"):
        return None
    name, _, extra = description[1:].partition(" ")
    if name not in skills:
        return None
    return name, extra.strip()


MAX_COMPLETION_META_LENGTH = 80


class SlashCommandCompleter(Completer):
    """Suggests slash commands, with their descriptions, while the user types '/'."""

    def __init__(self, commands: dict[str, str]):
        self.commands = commands

    def get_completions(
        self, document: Document, complete_event: CompleteEvent
    ) -> Iterable[Completion]:
        text = document.text_before_cursor
        if not text.startswith("/") or " " in text:
            return
        for command, description in self.commands.items():
            if command.startswith(text):
                yield Completion(
                    command,
                    start_position=-len(text),
                    display_meta=description[:MAX_COMPLETION_META_LENGTH],
                )


def make_prompt(commands: dict[str, str]) -> Callable[[], str]:
    """
    Returns a function that reads one line of input.
    In a terminal the line gets a dropdown of slash commands. Otherwise (piped
    input, tests) it falls back to a plain prompt.
    """
    if not sys.stdin.isatty():
        return lambda: click.prompt(">", default="", show_default=False)
    session: PromptSession[str] = PromptSession(
        completer=SlashCommandCompleter(commands), complete_while_typing=True
    )
    return lambda: session.prompt("> ")


def format_skills(skills: dict[str, Skill]) -> str:
    """Lists skills for the /skills command."""
    if not skills:
        return "No skills found."
    return "\n".join(
        f"- {skill.name}: {skill.description}" for skill in skills.values()
    )


def configure_logging(log_path: Path) -> None:
    """
    Sends all logs (structlog and stdlib, including openai/httpx) to a JSONL file.
    Only WARNING and above are echoed to stderr so the interactive TUI stays clean.
    """
    log_path.parent.mkdir(parents=True, exist_ok=True)

    shared_processors = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="ISO"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.UnicodeDecoder(),
    ]

    structlog.configure(
        processors=[
            *shared_processors,
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )

    file_handler = logging.FileHandler(log_path, encoding="utf-8")
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(
        structlog.stdlib.ProcessorFormatter(
            processor=structlog.processors.JSONRenderer(),
            foreign_pre_chain=shared_processors,
        )
    )

    console_handler = logging.StreamHandler(sys.stderr)
    console_handler.setLevel(logging.WARNING)
    console_handler.setFormatter(
        structlog.stdlib.ProcessorFormatter(
            processor=structlog.dev.ConsoleRenderer(colors=False),
            foreign_pre_chain=shared_processors,
        )
    )

    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(file_handler)
    root.addHandler(console_handler)
    root.setLevel(logging.DEBUG)


@click.command()
@click.option(
    "--session",
    "session_id",
    default=None,
    help="Resume an existing session by its id. A new session is created otherwise.",
)
@click.option(
    "--working-dir",
    "working_dir",
    default=None,
    type=click.Path(exists=True, file_okay=False, dir_okay=True, path_type=Path),
    help="Directory to run the agent in. Overrides AGENT_WORKING_DIR.",
)
def main(session_id: str | None, working_dir: Path | None):
    """
    Starts an interactive prompt that accepts tasks until you type 'exit' or 'quit'.
    """
    settings_kwargs: dict[str, Any] = {}
    if working_dir is not None:
        settings_kwargs["working_dir"] = working_dir

    try:
        settings = Settings(**settings_kwargs)
    except ValidationError as e:
        raise click.ClickException(f"Invalid configuration:\n{e}") from e

    if settings.working_dir is not None:
        try:
            os.chdir(settings.working_dir)
        except OSError as e:
            raise click.BadParameter(
                f"Cannot change to '{settings.working_dir}': {e}",
                param_hint="--working-dir",
            ) from e

    configure_logging(settings.log_file)

    try:
        session = (
            Session.load(session_id, root=settings.sessions_dir)
            if session_id
            else Session.create(root=settings.sessions_dir)
        )
    except (FileNotFoundError, ValueError) as e:
        raise click.BadParameter(str(e), param_hint="--session") from e

    structlog.contextvars.bind_contextvars(session_id=session.session_id)
    skills = discover_skills(default_skill_dirs())
    logger.info("Starting agent", current_working_directory=str(Path.cwd()))
    click.echo(f"Working dir: {Path.cwd()}")
    click.echo(f"Logs: {settings.log_file.resolve()}")
    click.echo(f"Session: {session.session_id}")
    click.echo(f"Skills: {', '.join(skills) or 'none'}")

    agent = Agent(
        openai_api_key=settings.openai_api_key.get_secret_value(),
        model=settings.model,
        session=session,
        base_url=settings.base_url,
        skills=skills,
    )

    commands = {
        SKILLS_COMMAND: "List available skills.",
        **dict.fromkeys(sorted(EXIT_COMMANDS), "Quit the agent."),
        **{f"/{name}": skill.description for name, skill in skills.items()},
    }
    read_input = make_prompt(commands)
    click.echo(
        f"Type a prompt, '{SKILLS_COMMAND}' to list skills, "
        "'/<skill name>' to run a skill, or '/exit' to quit."
    )
    while True:
        try:
            description = read_input().strip()
        except EOFError, KeyboardInterrupt, click.Abort:
            click.echo()
            break

        if description.lower() in EXIT_COMMANDS:
            break
        if not description:
            continue
        if description == SKILLS_COMMAND:
            click.echo(format_skills(skills))
            continue

        skill_command = parse_skill_command(description, skills)
        if skill_command is not None:
            skill_name, extra = skill_command
            skill = skills[skill_name]
            request = extra or "none provided"
            try:
                instructions = skill.path.read_text(encoding="utf-8")
            except OSError as e:
                click.echo(f"Cannot read skill '{skill.name}': {e}")
                logger.error("Failed to read skill", skill=skill.name, error=str(e))
                continue
            task = Task(
                description=f"Run the '{skill.name}' skill. Request details: {request}",
                instructions=instructions,
                max_iterations=settings.max_iterations,
            )
        else:
            task = Task(description=description, max_iterations=settings.max_iterations)

        logger.info("Running task", task=task.description)
        try:
            agent.run_task(task)
        except KeyboardInterrupt:
            click.echo("\nTask interrupted.")

    click.echo("Goodbye.")


if __name__ == "__main__":
    main()
