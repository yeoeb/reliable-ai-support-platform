from pydantic import BaseModel, ConfigDict, Field, field_validator


MAX_AGENT_REQUEST_CHARS = 4000


class AgentRunRequest(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
    )

    request: str = Field(
        min_length=1,
        max_length=MAX_AGENT_REQUEST_CHARS,
    )

    @field_validator("request", mode="before")
    @classmethod
    def validate_raw_request_length(
        cls,
        value: object,
    ) -> object:
        if (
            isinstance(value, str)
            and len(value) > MAX_AGENT_REQUEST_CHARS
        ):
            raise ValueError(
                "Agent request exceeds maximum length"
            )
        return value


class AgentRunResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    answer: str
    tool_used: str | None
    tool_status: str | None
    model: str
    input_tokens: int = Field(ge=0)
    output_tokens: int = Field(ge=0)
