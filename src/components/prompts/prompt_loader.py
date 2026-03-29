"""
Loads ChatPromptTemplates from YAML prompt files for use with LangChain LLMs.
"""

import yaml
from langchain_core.prompts import ChatPromptTemplate

from src.errors.custom_exceptions import server_error
from src.logger.base_logger import BaseLogger

logger = BaseLogger(__name__)


def create_prompt_template(prompt_filepath):
    """
    Creates a LangChain ChatPromptTemplate from a YAML file.

    The YAML file must contain 'system' and 'user' keys:
    (1) system: Instructions for the AI's behavior and role
    (2) user: Template for the user's input (can include placeholders like {context}, {query})

    Args:
        prompt_filepath (str): Path to the YAML prompt file

    Returns:
        ChatPromptTemplate: Ready-to-use LangChain prompt template

    Usage:
        prompt = create_prompt_template("prompts/my_prompt.yaml")
        chain = prompt | llm | output_parser
        response = chain.invoke({"context": "...", "query": "..."})

    YAML Format:
        system: |
            You are a helpful assistant that...
        user: |
            Context: {context}
            Question: {query}
    """

    # Open and parse the YAML prompt file
    try:
        with open(prompt_filepath, "r", encoding="utf-8") as f:
            prompt_data = yaml.safe_load(f)
    except Exception as e:
        raise server_error(
            message="Failed to load prompt template.",
            error_code="PROMPT_TEMPLATE_LOAD_ERROR",
            stack_trace=str(e),
        )

    logger.debug("Prompt loaded and prompt template created.")

    # Create a LangChain ChatPromptTemplate using the parsed message templates
    return ChatPromptTemplate.from_messages(
        [
            ("system", prompt_data["system"]),  # Set assistant behavior
            ("user", prompt_data["user"]),  # Set user query format
        ]
    )
