from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel

from app.core.errors import UnknownToolError
from app.integrations.llm import ToolSpec


ToolRisk = Literal["read_only"]
ToolExecutor = Callable[[BaseModel], dict[str, str]]


@dataclass(frozen=True)
class ToolDefinition:
    name: str
    description: str
    required_permission: str
    risk_level: ToolRisk
    arguments_model: type[BaseModel]
    executor: ToolExecutor

    def provider_spec(self) -> ToolSpec:
        schema = self.arguments_model.model_json_schema()
        properties = schema.get("properties", {})
        schema["properties"] = properties
        schema["required"] = list(properties.keys())
        schema["additionalProperties"] = False
        schema.pop("title", None)
        return ToolSpec(
            name=self.name,
            description=self.description,
            parameters=schema,
        )


class ToolRegistry:
    def __init__(
        self,
        definitions: list[ToolDefinition],
    ) -> None:
        registry: dict[str, ToolDefinition] = {}
        for definition in definitions:
            if not definition.name.strip():
                raise ValueError("Tool name must not be empty")
            if definition.risk_level != "read_only":
                raise ValueError(
                    "Issue 015 registry accepts read-only tools only"
                )
            if definition.name in registry:
                raise ValueError(
                    f"Duplicate tool name: {definition.name}"
                )
            registry[definition.name] = definition
        self._definitions = registry

    def get(self, name: str) -> ToolDefinition:
        try:
            return self._definitions[name]
        except KeyError as exc:
            raise UnknownToolError(
                "Unknown tool"
            ) from exc

    def authorized_for_permissions(
        self,
        permissions: set[str],
    ) -> list[ToolDefinition]:
        return [
            definition
            for definition in self._definitions.values()
            if definition.required_permission in permissions
        ]
