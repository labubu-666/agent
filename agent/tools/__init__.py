from .base import Tool
from .console import PrintToConsoleTool
from .files import CreateFileTool, EditFileTool, ListFilesTool, ReadFileTool
from .http import HttpRequestTool
from .image import ReadImageTool
from .replace import ReplaceTextInFileTool
from .search import SearchTextInDirectoryTool
from .shell import RunCommandTool
from .skill import UseSkillTool
from .timestamp import CurrentISOTimestamp

# Register all tools
TOOL_REGISTRY: dict[str, Tool] = {
    tool.name: tool
    for tool in [
        CurrentISOTimestamp(),
        PrintToConsoleTool(),
        SearchTextInDirectoryTool(),
        ReplaceTextInFileTool(),
        ListFilesTool(),
        ReadFileTool(),
        CreateFileTool(),
        EditFileTool(),
        RunCommandTool(),
        HttpRequestTool(),
        ReadImageTool(),
    ]
}

__all__ = [
    "TOOL_REGISTRY",
    "CreateFileTool",
    "CurrentISOTimestamp",
    "EditFileTool",
    "HttpRequestTool",
    "ListFilesTool",
    "PrintToConsoleTool",
    "ReadFileTool",
    "ReadImageTool",
    "ReplaceTextInFileTool",
    "RunCommandTool",
    "SearchTextInDirectoryTool",
    "Tool",
    "UseSkillTool",
]
