"""Discovers Claude- and OpenCode-style skills: folders containing a SKILL.md with YAML front matter."""

import re
from pathlib import Path
from typing import Any

import structlog
import yaml
from pydantic import BaseModel, Field

logger = structlog.get_logger(__name__)

SKILL_FILE_NAME = "SKILL.md"
MAX_NAME_LENGTH = 64
MAX_DESCRIPTION_LENGTH = 1024
_NAME_PATTERN = re.compile(r"^[a-z0-9-]+$")


class Skill(BaseModel):
    """A skill loaded from a SKILL.md file."""

    name: str = Field(..., description="The unique name of the skill.")
    description: str = Field(..., description="When the skill should be used.")
    path: Path = Field(..., description="Absolute path to the SKILL.md file.")
    directory: Path = Field(..., description="Absolute path to the skill folder.")
    metadata: dict[str, Any] = Field(
        default_factory=dict, description="Other front matter fields, kept as-is."
    )


def default_skill_dirs() -> list[Path]:
    """Returns the skill folders in priority order: project first, then user.

    Within each level, `.claude` wins over `.opencode`.
    """
    home = Path.home()
    return [
        Path(".claude") / "skills",
        Path(".opencode") / "skills",
        home / ".claude" / "skills",
        home / ".config" / "opencode" / "skills",
    ]


def _split_front_matter(text: str) -> str:
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        raise ValueError("SKILL.md must start with a '---' YAML front matter block.")
    for index in range(1, len(lines)):
        if lines[index].strip() == "---":
            return "\n".join(lines[1:index])
    raise ValueError("SKILL.md front matter is missing its closing '---' line.")


def parse_skill_file(path: Path) -> Skill:
    """Parses a SKILL.md file. Raises ValueError if it is not a valid skill."""
    path = path.resolve()
    front_matter = yaml.safe_load(_split_front_matter(path.read_text(encoding="utf-8")))
    if not isinstance(front_matter, dict):
        raise ValueError("SKILL.md front matter must be a YAML mapping.")

    name = front_matter.get("name")
    description = front_matter.get("description")
    if not isinstance(name, str) or not name.strip():
        raise ValueError("Skill is missing a 'name'.")
    if not isinstance(description, str) or not description.strip():
        raise ValueError("Skill is missing a 'description'.")

    name = name.strip()
    description = description.strip()
    if len(name) > MAX_NAME_LENGTH or not _NAME_PATTERN.match(name):
        raise ValueError(
            f"Invalid skill name '{name}': use lowercase letters, digits and hyphens, "
            f"at most {MAX_NAME_LENGTH} characters."
        )
    if len(description) > MAX_DESCRIPTION_LENGTH:
        raise ValueError(
            f"Skill description is longer than {MAX_DESCRIPTION_LENGTH} characters."
        )

    metadata = {
        key: value
        for key, value in front_matter.items()
        if key not in ("name", "description")
    }
    return Skill(
        name=name,
        description=description,
        path=path,
        directory=path.parent,
        metadata=metadata,
    )


def discover_skills(dirs: list[Path]) -> dict[str, Skill]:
    """Finds skills in each `<dir>/*/SKILL.md`. Earlier directories win on name clashes."""
    skills: dict[str, Skill] = {}
    for root in dirs:
        if not root.is_dir():
            continue
        for skill_file in sorted(root.glob(f"*/{SKILL_FILE_NAME}")):
            try:
                skill = parse_skill_file(skill_file)
            except (OSError, yaml.YAMLError, ValueError) as e:
                logger.warning(
                    "Skipping invalid skill", path=str(skill_file), error=str(e)
                )
                continue
            if skill.name in skills:
                logger.warning(
                    "Skipping duplicate skill",
                    name=skill.name,
                    path=str(skill_file),
                    kept=str(skills[skill.name].path),
                )
                continue
            skills[skill.name] = skill
    return dict(sorted(skills.items()))
