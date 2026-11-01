from typing import Any

from pydantic import BaseModel


class Tool:
    """Base class for all tools. Subclasses set `name`, `description` and `args_schema`."""

    name: str
    description: str
    args_schema: type[BaseModel]

    def run(self, **kwargs: Any) -> str:
        raise NotImplementedError
