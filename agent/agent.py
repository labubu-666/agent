import json
import re
import subprocess
from pathlib import Path
from typing import Any, Literal, cast

import requests
import structlog
from openai import OpenAI
from openai.types.chat import ChatCompletionMessageParam
from pydantic import BaseModel, Field, ValidationError
from ripgrepy import RipGrepNotFound

from .agents_md import (
    PATH_ARGUMENT_NAMES,
    load_startup_instructions,
    load_subdirectory_instructions,
)
from .session import Session
from .skills import Skill
from .tools import TOOL_REGISTRY, Tool, UseSkillTool
from .tools.image import ImageLoadError, load_image_data_uri

logger = structlog.get_logger(__name__)

_TOOL_CALL_PATTERN = re.compile(r"<tool_call>\s*(.*?)\s*</tool_call>", re.DOTALL)
_REASONING_PATTERN = re.compile(r"<reasoning>(.*?)</reasoning>", re.DOTALL)


class ToolCall(BaseModel):
    """Represents a call to a specific tool."""

    tool_name: str = Field(..., description="The name of the tool to call.")
    arguments: dict[str, Any] = Field(
        ..., description="A dictionary of arguments for the tool."
    )


class AgentAction(BaseModel):
    """The action the agent decides to take."""

    action: Literal["call_tool", "finish"] = Field(
        ...,
        description="'call_tool' to use a tool, or 'finish' when the task is complete.",
    )
    tool_call: ToolCall | None = Field(
        None, description="Details if the action is 'call_tool'."
    )
    final_answer: str | None = Field(
        None, description="The final answer if the action is 'finish'."
    )
    # Optional: models sometimes omit it, and a missing field should not end the task.
    reasoning: str = Field("", description="The agent's reasoning for this action.")


class Task(BaseModel):
    """The initial task given to the agent."""

    description: str = Field(
        ..., description="A clear description of the task to be performed."
    )
    instructions: str = Field(
        "", description="Extra instructions for the model, e.g. a skill's SKILL.md."
    )
    max_iterations: int = Field(
        ..., description="Maximum number of iterations before stopping."
    )
    image_paths: list[str] = Field(
        default_factory=list,
        description="Absolute paths of images attached to the task, sent with the first message.",
    )


class Agent:
    def __init__(
        self,
        openai_api_key: str,
        model: str,
        session: Session | None = None,
        base_url: str | None = None,
        skills: dict[str, Skill] | None = None,
        working_dir: Path | None = None,
        home_dir: Path | None = None,
    ):
        self.client = OpenAI(api_key=openai_api_key, base_url=base_url)
        self.model = model
        self.session = session or Session.create()
        self.skills = skills or {}
        # None means the current working directory and the user's home directory.
        self.working_dir = working_dir
        self.home_dir = home_dir
        # Resolved paths of instruction files already sent to the model in this task.
        self.loaded_instruction_files: set[Path] = set()
        self.tools: dict[str, Tool] = dict(TOOL_REGISTRY)
        if self.skills:
            self.tools[UseSkillTool.name] = UseSkillTool(self.skills)
        # The system prompt is not persisted; it is rebuilt on every request.
        # Error entries are kept in the file for debugging but never sent to the API.
        self.chat_history: list[ChatCompletionMessageParam] = [
            self._build_message(m.role, m.content, m.image_paths)
            for m in self.session.messages()
            if m.role != "error"
        ]

    @staticmethod
    def _build_message(
        role: str, content: str, image_paths: list[str] | None = None
    ) -> ChatCompletionMessageParam:
        """Builds a chat message. Messages with images use content parts with image_url items.

        Images are read from disk here. An image that can no longer be loaded is replaced
        with a text note so that the rest of the history still works.
        """
        if not image_paths:
            return cast(ChatCompletionMessageParam, {"role": role, "content": content})

        parts: list[dict[str, Any]] = [{"type": "text", "text": content}]
        for image_path in image_paths:
            try:
                data_uri = load_image_data_uri(Path(image_path))
            except ImageLoadError as e:
                parts.append(
                    {"type": "text", "text": f"[Image '{image_path}' unavailable: {e}]"}
                )
                continue
            parts.append({"type": "image_url", "image_url": {"url": data_uri}})
        return cast(ChatCompletionMessageParam, {"role": role, "content": parts})

    def _record(
        self,
        role: Literal["user", "assistant"],
        content: str,
        image_paths: list[str] | None = None,
    ) -> None:
        """Adds a message to the in-memory history and persists it to the session."""
        self.chat_history.append(self._build_message(role, content, image_paths))
        self.session.append(role, content, self.model, image_paths)

    def _record_error(self, error: Exception) -> None:
        """Persists a failure to the session file without adding it to the chat history."""
        self.session.append("error", f"{type(error).__name__}: {error}", self.model)

    def _call_llm(self, system_prompt: str) -> str:
        response = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": system_prompt},
                *self.chat_history,
            ],
            temperature=0.5,
            response_format={"type": "json_object"},
        )
        content = response.choices[0].message.content
        if not content:
            raise ValueError("Received empty content from LLM.")
        return content

    @staticmethod
    def _parse_xml_tool_call(content: str) -> AgentAction | None:
        """Parses a '<tool_call>{...}</tool_call>' reply. Returns None if it doesn't match."""
        match = _TOOL_CALL_PATTERN.search(content)
        if match is None:
            return None
        try:
            tool_call = ToolCall.model_validate_json(match.group(1))
        except ValidationError:
            return None
        reasoning = _REASONING_PATTERN.search(content)
        return AgentAction(
            action="call_tool",
            tool_call=tool_call,
            reasoning=reasoning.group(1).strip() if reasoning else "",
        )

    @staticmethod
    def _parse_action(content: str) -> AgentAction:
        try:
            return AgentAction.model_validate_json(content)
        except ValidationError:
            # Some models answer in an XML-style format instead of JSON.
            xml_action = Agent._parse_xml_tool_call(content)
            if xml_action is not None:
                return xml_action
            # The model sometimes wraps the JSON object in extra prose, and that
            # prose may contain braces (e.g. "{pk}"). Try each '{' in turn and
            # return the first one that decodes to a valid AgentAction.
            decoder = json.JSONDecoder()
            for match in re.finditer(r"\{", content):
                try:
                    obj, _ = decoder.raw_decode(content, match.start())
                    return AgentAction.model_validate(obj)
                except json.JSONDecodeError, ValidationError:
                    continue
            raise

    def _get_llm_response(
        self,
        system_prompt: str,
        user_prompt: str,
        image_paths: list[str] | None = None,
    ) -> AgentAction | str:
        """Sends the prompt and parses the reply.

        Returns the parsed action. If the reply cannot be parsed, returns a correction
        message to send back to the model. An API failure ends the task via a 'finish' action.
        """
        self._record("user", user_prompt, image_paths)
        try:
            content = self._call_llm(system_prompt)
        except Exception as e:
            logger.exception("LLM call failed")
            self._record_error(e)
            print(f"Error: {e}")
            return AgentAction(
                action="finish",
                tool_call=None,
                final_answer=f"An internal error occurred: Error calling LLM: {e}. Cannot continue.",
                reasoning="An error prevented the agent from continuing.",
            )

        self._record("assistant", content)
        try:
            return self._parse_action(content)
        except ValidationError as e:
            logger.warning("Could not parse LLM reply", error=str(e))
            self._record_error(e)
            print(f"Error: could not parse LLM reply: {e}")
            return (
                "Your last reply was not valid. Respond only with a JSON object matching the "
                f"AgentAction schema. Parsing failed with: {e}. Please try again."
            )

    def _build_system_prompt(self, project_instructions: str | None = None) -> str:
        tool_descriptions = [
            f"- {name}: {tool.description}\n  Parameters: {tool.args_schema.model_json_schema()}"
            for name, tool in self.tools.items()
        ]
        skills_section = ""
        if self.skills:
            skill_lines = [
                f"- {skill.name}: {skill.description}" for skill in self.skills.values()
            ]
            skills_section = (
                "\n\nAvailable skills (specialized instructions you can load):\n"
                + "\n".join(skill_lines)
                + "\nIf a task matches a skill's description, call the 'use_skill' tool "
                "with the skill's name first and follow its instructions."
            )
        instructions_section = ""
        if project_instructions:
            instructions_section = (
                "\n\nProject instructions (from AGENTS.md and CLAUDE.md files). "
                "Follow them. Where files conflict, later files are more specific "
                "and take precedence.\n" + project_instructions
            )
        return (
            "You are an AI assistant designed to help with tasks by using available tools. "
            "Your goal is to complete the user's request. "
            "When you have finished the task and have a final answer, set 'action' to 'finish' "
            "and provide your 'final_answer'. "
            "Always provide your 'reasoning' for each step. "
            "\nAvailable tools:\n"
            + "\n".join(tool_descriptions)
            + skills_section
            + instructions_section
            + "\n\nYou must always respond with valid JSON matching this AgentAction schema:\n"
            + f"{AgentAction.model_json_schema()}"
        )

    def _run_tool(self, tool_call: ToolCall) -> tuple[str, list[str]]:
        """Runs a tool and returns the observation to send back to the model.

        Also returns any image paths the tool attached to the observation.
        """
        tool_name = tool_call.tool_name
        arguments = tool_call.arguments
        print(f"\n--- Calling {tool_name} with arguments {arguments} ---")

        if tool_name not in self.tools:
            observation = f"Error: Tool '{tool_name}' not found. Available tools are: {list(self.tools.keys())}"
            print(f"Tool Error: {observation}")
            return (
                f"Your last tool call failed. Observation: {observation}. Please reconsider your next action.",
                [],
            )

        tool = self.tools[tool_name]
        try:
            validated_args = tool.args_schema.model_validate(arguments)
            output = tool.execute(**validated_args.model_dump())
            print(f"Tool '{tool_name}' executed successfully.")
            instructions = self._subdirectory_instructions(arguments)
            suffix = f"\n\n{instructions}" if instructions else ""
            return (
                f"Tool '{tool_name}' executed. Observation: {output.text}{suffix}\n\nWhat is your next action to fulfill the task?",
                output.image_paths,
            )
        except (
            OSError,
            ValueError,
            subprocess.SubprocessError,
            requests.RequestException,
            ImageLoadError,
            RipGrepNotFound,
        ) as e:
            observation = (
                f"Error running tool '{tool_name}': {e}. Arguments: {arguments}"
            )
            print(f"Tool Execution Error: {observation}")
            return (
                f"Tool '{tool_name}' execution failed. Observation: {observation}. Please reconsider your next action.",
                [],
            )

    def _working_dir(self) -> Path:
        return self.working_dir or Path.cwd()

    def _home_dir(self) -> Path:
        return self.home_dir or Path.home()

    def _subdirectory_instructions(self, arguments: dict[str, Any]) -> str:
        """Returns AGENTS.md/CLAUDE.md text for folders below the working directory that a
        tool argument points into and that this task has not loaded yet."""
        texts = []
        for name in PATH_ARGUMENT_NAMES:
            value = arguments.get(name)
            if isinstance(value, str) and value:
                texts.append(
                    load_subdirectory_instructions(
                        self._working_dir(),
                        Path(value),
                        self.loaded_instruction_files,
                    )
                )
        return "\n\n".join(text for text in texts if text)

    def run_task(self, task: Task) -> str | None:
        """Executes the given task iteratively until completion or max iterations reached."""
        print(f"--- Starting task ---\n{task.description}\n---------------------")

        project_instructions, self.loaded_instruction_files = load_startup_instructions(
            self._working_dir(), self._home_dir()
        )
        system_prompt = self._build_system_prompt(project_instructions)
        user_prompt = f"Begin the task: {task.description}"
        if task.instructions:
            user_prompt += f"\n\nInstructions:\n{task.instructions}"

        image_paths: list[str] = list(task.image_paths)
        for i in range(task.max_iterations):
            print(f"\n--- Iteration {i + 1}/{task.max_iterations} ---")

            response = self._get_llm_response(system_prompt, user_prompt, image_paths)
            image_paths = []
            if isinstance(response, str):
                user_prompt = response
                continue
            agent_action = response
            print(f"💡 {agent_action.reasoning}")
            print(f"Agent Action: {agent_action.action}")

            if agent_action.action == "finish":
                print("\n--- Task Complete! ---")
                print(f"Final Answer: {agent_action.final_answer}")
                return agent_action.final_answer

            if agent_action.tool_call is None:
                print(
                    "Error: Agent decided to call a tool but no tool_call details were provided."
                )
                user_prompt = "Error: You indicated 'call_tool' but did not provide 'tool_call' details. Please correct your response."
                continue

            user_prompt, image_paths = self._run_tool(agent_action.tool_call)

        print(
            f"\n--- Max iterations ({task.max_iterations}) reached. Task not completed. ---"
        )
        return "Task not completed within the allowed iterations."
