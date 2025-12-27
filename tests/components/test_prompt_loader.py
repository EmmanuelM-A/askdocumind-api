"""
Unit tests for the prompt_loader module.
Tests YAML loading and ChatPromptTemplate creation.
"""

from pathlib import Path

import pytest

from src.components.prompts.prompt_loader import create_prompt_template
from src.errors.api_exceptions import ApiException


def test_create_prompt_template_success(tmp_path):
    """Test successful prompt template creation from valid YAML file."""
    # Create a temporary YAML file
    yaml_content = """system: |
    You are a helpful assistant.
user: |
    Context: {context}
    Question: {query}
"""
    yaml_file = tmp_path / "test_prompt.yaml"
    yaml_file.write_text(yaml_content, encoding="utf-8")

    template = create_prompt_template(str(yaml_file))

    assert template is not None
    assert hasattr(template, "invoke")
    assert hasattr(template, "format_messages")


def test_create_prompt_template_with_actual_prompt_file():
    """Test loading the actual default_response_prompt.yaml file."""

    # Get the actual prompt file path
    project_root = Path(__file__).parent.parent.parent
    prompt_file = project_root / "prompts" / "default_response_prompt.yaml"

    if prompt_file.exists():
        template = create_prompt_template(str(prompt_file))

        assert template is not None
        # Verify the template has the expected structure
        messages = template.format_messages(context="Test context", query="Test query")
        assert len(messages) == 2  # system and user messages
        assert messages[0].type == "system"
        assert messages[1].type == "human"


def test_create_prompt_template_file_not_found():
    """Test that non-existent file raises server error."""
    with pytest.raises(ApiException) as exc_info:
        create_prompt_template("non_existent_file.yaml")

    assert exc_info.value.error.code == "PROMPT_TEMPLATE_LOAD_ERROR"


def test_create_prompt_template_invalid_yaml(tmp_path):
    """Test that invalid YAML raises server error."""
    # Create a file with invalid YAML
    yaml_file = tmp_path / "invalid.yaml"
    yaml_file.write_text("invalid: yaml: content: [unclosed", encoding="utf-8")

    with pytest.raises(ApiException) as exc_info:
        create_prompt_template(str(yaml_file))

    assert exc_info.value.error.code == "PROMPT_TEMPLATE_LOAD_ERROR"


def test_create_prompt_template_missing_system_key(tmp_path):
    """Test that YAML missing 'system' key raises error."""
    yaml_content = """user: |
    Question: {query}
"""
    yaml_file = tmp_path / "missing_system.yaml"
    yaml_file.write_text(yaml_content, encoding="utf-8")

    with pytest.raises(KeyError):
        create_prompt_template(str(yaml_file))


def test_create_prompt_template_missing_user_key(tmp_path):
    """Test that YAML missing 'user' key raises error."""
    yaml_content = """system: |
    You are a helpful assistant.
"""
    yaml_file = tmp_path / "missing_user.yaml"
    yaml_file.write_text(yaml_content, encoding="utf-8")

    with pytest.raises(KeyError):
        create_prompt_template(str(yaml_file))


def test_create_prompt_template_with_placeholders(tmp_path):
    """Test that template correctly handles placeholders."""
    yaml_content = """system: |
    You are a helpful assistant.
user: |
    Context: {context}
    Question: {query}
"""
    yaml_file = tmp_path / "with_placeholders.yaml"
    yaml_file.write_text(yaml_content, encoding="utf-8")

    template = create_prompt_template(str(yaml_file))

    # Test that placeholders can be filled
    messages = template.format_messages(
        context="Sample context text", query="What is this about?"
    )

    assert len(messages) == 2
    assert "Sample context text" in messages[1].content
    assert "What is this about?" in messages[1].content
