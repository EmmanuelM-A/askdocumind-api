import logging
from pathlib import Path
from typing import Any

import yaml
from langchain_core.prompts import ChatPromptTemplate

from src.exceptions import server_error

_logger = logging.getLogger(__name__)


def load_prompt_from(path: str | Path) -> ChatPromptTemplate:
    """
    Load a prompt from a YAML file and return it as a ChatPromptTemplate.
    """
    path = Path(path)

    try:
        with path.open("r", encoding="utf-8") as file:
            prompt_data: Any = yaml.safe_load(file)

        if not isinstance(prompt_data, dict):
            raise ValueError("The prompt YAML must be a dictionary")

        system_prompt = prompt_data.get("system", None)
        user_prompt = prompt_data.get("user", None)

        if system_prompt is None or user_prompt is None:
            raise ValueError("Prompt YAML must contain both 'system' and 'user' keys")

        if not isinstance(system_prompt, str) or not system_prompt.strip():
            raise ValueError("Prompt must contain a non-empty 'system' string")

        if not isinstance(user_prompt, str) or not user_prompt.strip():
            raise ValueError("Prompt must contain a non-empty 'user' string")

        prompt = ChatPromptTemplate.from_messages(
            [
                ("system", system_prompt),
                ("user", user_prompt),
            ]
        )

    except Exception as e:
        raise server_error(
            message=f"Failed to load prompt from {path}",
            error_code="PROMPT_LOAD_ERROR",
            error_details={"reason": str(e)},
        ) from e

    _logger.info(f"Prompt loaded successfully from {path}")

    return prompt
