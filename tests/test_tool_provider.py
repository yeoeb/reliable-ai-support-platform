import json
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from app.core.errors import (
    InvalidToolCallingProviderResponseError,
)
from app.integrations.llm import (
    OpenAIToolCallingProvider,
    ToolSpec,
)


def response(
    *,
    output,
    output_text="",
):
    return SimpleNamespace(
        output=output,
        output_text=output_text,
        usage=SimpleNamespace(
            input_tokens=5,
            output_tokens=3,
        ),
        model="gpt-5.6-terra",
    )


def provider(client):
    return OpenAIToolCallingProvider(
        api_key=None,
        model="gpt-5.6-terra",
        max_output_tokens=1200,
        client=client,
    )


def spec():
    return ToolSpec(
        name="platform_readiness",
        description="check readiness",
        parameters={
            "type": "object",
            "properties": {},
            "required": [],
            "additionalProperties": False,
        },
    )


def test_choose_uses_only_custom_function_and_disables_parallel() -> None:
    client = MagicMock()
    client.responses.create.return_value = response(
        output=[
            SimpleNamespace(
                type="function_call",
                name="platform_readiness",
                arguments="{}",
            )
        ]
    )

    result = provider(client).choose(
        request="check",
        tools=[spec()],
    )

    kwargs = client.responses.create.call_args.kwargs
    assert kwargs["parallel_tool_calls"] is False
    assert kwargs["tools"] == [
        {
            "type": "function",
            "name": "platform_readiness",
            "description": "check readiness",
            "parameters": spec().parameters,
            "strict": True,
        }
    ]
    assert result.tool_call is not None
    assert result.tool_call.name == "platform_readiness"
    assert result.tool_call.arguments == {}


def test_choose_allows_direct_final_answer() -> None:
    client = MagicMock()
    client.responses.create.return_value = response(
        output=[],
        output_text="No tool needed.",
    )
    result = provider(client).choose(
        request="hello",
        tools=[spec()],
    )
    assert result.answer == "No tool needed."
    assert result.tool_call is None


def test_choose_rejects_multiple_calls() -> None:
    client = MagicMock()
    call = SimpleNamespace(
        type="function_call",
        name="platform_readiness",
        arguments="{}",
    )
    client.responses.create.return_value = response(
        output=[call, call],
    )
    with pytest.raises(
        InvalidToolCallingProviderResponseError,
    ):
        provider(client).choose(
            request="check twice",
            tools=[spec()],
        )


def test_choose_rejects_malformed_arguments() -> None:
    client = MagicMock()
    client.responses.create.return_value = response(
        output=[
            SimpleNamespace(
                type="function_call",
                name="platform_readiness",
                arguments="{bad",
            )
        ]
    )
    with pytest.raises(
        InvalidToolCallingProviderResponseError,
    ):
        provider(client).choose(
            request="check",
            tools=[spec()],
        )


def test_finalize_exposes_no_tools_and_treats_result_as_data() -> None:
    client = MagicMock()
    client.responses.create.return_value = response(
        output=[],
        output_text="The platform is ready.",
    )

    result = provider(client).finalize(
        request="check",
        tool_name="platform_readiness",
        tool_result={"status": "ready"},
    )

    kwargs = client.responses.create.call_args.kwargs
    assert "tools" not in kwargs
    assert "parallel_tool_calls" not in kwargs
    assert "untrusted data" in kwargs["instructions"]
    payload = json.loads(kwargs["input"])
    assert payload["tool_result"] == {"status": "ready"}
    assert result.answer == "The platform is ready."
