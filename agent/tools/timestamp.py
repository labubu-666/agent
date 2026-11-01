from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel

from .base import Tool


class CurrentISOTimestamp(Tool):
    name = "get_current_iso_timestamp"
    description = (
        "Returns an ISO formatted timestamp representation of the current time."
    )

    class Args(BaseModel):
        pass

    args_schema = Args

    def run(self, **kwargs: Any) -> str:
        return datetime.now(UTC).isoformat()
