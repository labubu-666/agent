from typing import Any

from pydantic import BaseModel, Field

from ..skills import Skill
from .base import Tool


class UseSkillTool(Tool):
    """A tool to load the full instructions of a discovered skill."""

    name = "use_skill"
    description = (
        "Loads the full instructions of an available skill by name. "
        "Call this before doing a task that matches a skill's description."
    )

    class Args(BaseModel):
        skill_name: str = Field(description="The name of the skill to load.")

    args_schema = Args

    def __init__(self, skills: dict[str, Skill]):
        self.skills = skills

    def run(self, **kwargs: Any) -> str:
        skill_name = kwargs.get("skill_name", "")
        skill = self.skills.get(skill_name)
        if skill is None:
            return (
                f"Error: Skill '{skill_name}' not found. "
                f"Available skills are: {list(self.skills.keys())}"
            )

        other_files = sorted(
            str(path.relative_to(skill.directory))
            for path in skill.directory.rglob("*")
            if path.is_file() and path != skill.path
        )
        files_text = "\n".join(f"- {file}" for file in other_files) or "(none)"
        instructions = skill.path.read_text(encoding="utf-8")
        return (
            f"Skill: {skill.name}\n"
            f"Directory: {skill.directory}\n"
            f"Other files in this skill (read them with read_file, or run scripts "
            f"with run_command using absolute paths):\n{files_text}\n\n"
            f"Instructions:\n{instructions}"
        )
