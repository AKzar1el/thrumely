from thrumely import anthropic_controller, openai_controller
from thrumely.schema import ToolEnvironment


def _chooser_environment() -> ToolEnvironment:
    return ToolEnvironment(
        "chooser",
        "chooser",
        (
            "openai:gpt-image-2",
            "google:gemini-3.1-flash-image",
            "bfl:flux-2-pro",
        ),
    )


def test_controller_system_prompt_is_identical_across_providers() -> None:
    assert anthropic_controller.SYSTEM_PROMPT == openai_controller.SYSTEM_PROMPT


def test_media_tool_semantics_are_identical_across_providers() -> None:
    environment = _chooser_environment()
    openai_tool = openai_controller._media_tool(environment, allow_edit=True)
    anthropic_tool = anthropic_controller._media_tool(environment, allow_edit=True)

    assert anthropic_tool["description"] == openai_tool["description"]
    assert anthropic_tool["input_schema"] == openai_tool["parameters"]


def test_finish_tool_semantics_are_identical_across_providers() -> None:
    openai_tool = openai_controller._finish_tool()
    anthropic_tool = anthropic_controller._finish_tool()

    assert anthropic_tool["description"] == openai_tool["description"]
    assert anthropic_tool["input_schema"] == openai_tool["parameters"]
