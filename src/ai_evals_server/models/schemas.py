from datetime import datetime
from enum import Enum
from typing import Any
from pydantic import BaseModel, ConfigDict, Field, field_validator


# ---------------------------------------------------------------------------
# Prompt
# ---------------------------------------------------------------------------

class PromptCreate(BaseModel):
    name: str
    prompt_string: str = ''  # used only to seed v1, not stored on the prompt record
    tools: list[str] = Field(default_factory=list)
    use_responses_api: bool = False
    connection_id: str | None = None
    max_output_tokens: int | None = None
    model: str | None = None
    mcp_server_id: str | None = None
    mcp_tool_filter: list[str] | None = None  # null = all tools allowed


class PromptUpdate(BaseModel):
    name: str | None = None
    tools: list[str] | None = None
    use_responses_api: bool | None = None
    connection_id: str | None = None
    max_output_tokens: int | None = None
    model: str | None = None
    mcp_server_id: str | None = None
    mcp_tool_filter: list[str] | None = None


class Prompt(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    tools: list[str]
    use_responses_api: bool
    connection_id: str | None = None
    max_output_tokens: int | None = None
    model: str | None = None
    mcp_server_id: str | None = None
    mcp_tool_filter: list[str] | None = None
    created_at: datetime
    created_by_email: str | None = None
    latest_version_string: str | None = None  # derived from latest version


class PromptVersionCreate(BaseModel):
    prompt_string: str
    version_number: int


class PromptVersionUpdate(BaseModel):
    prompt_string: str


class PromptVersion(PromptVersionCreate):
    model_config = ConfigDict(from_attributes=True)

    id: str
    prompt_id: str
    created_at: datetime


# ---------------------------------------------------------------------------
# Dataset
# ---------------------------------------------------------------------------

class DatasetRowCreate(BaseModel):
    input: str
    comment: str = ""


class DatasetRowUpdate(BaseModel):
    input: str | None = None
    comment: str | None = None


class DatasetRow(DatasetRowCreate):
    model_config = ConfigDict(from_attributes=True)

    id: str
    created_at: datetime


class DatasetCreate(BaseModel):
    name: str


class DatasetUpdate(BaseModel):
    name: str | None = None


class Dataset(DatasetCreate):
    model_config = ConfigDict(from_attributes=True)

    id: str
    rows: list[DatasetRow] = Field(default_factory=list)
    created_at: datetime
    created_by_email: str | None = None


# ---------------------------------------------------------------------------
# Scorer
# ---------------------------------------------------------------------------

class ScorerCreate(BaseModel):
    name: str
    # Template: use {input} for original input, {output} for prompt output.
    prompt_string: str
    model: str = "claude-sonnet-4-6"
    connection_id: str | None = None
    pass_threshold: int = 7


class ScorerUpdate(BaseModel):
    name: str | None = None
    prompt_string: str | None = None
    model: str | None = None
    connection_id: str | None = None
    pass_threshold: int | None = None


class Scorer(ScorerCreate):
    model_config = ConfigDict(from_attributes=True)

    id: str
    created_at: datetime
    created_by_email: str | None = None


# ---------------------------------------------------------------------------
# Connection
# ---------------------------------------------------------------------------

class ConnectionType(str, Enum):
    claude = "claude"
    openai = "openai"           # Chat Completions API (also supports Responses API via use_responses_api flag)
    azure_openai = "azure_openai"           # Chat Completions API



class ConnectionCreate(BaseModel):
    name: str
    type: ConnectionType
    api_key: str
    # Azure OpenAI extras
    azure_endpoint: str | None = None       # e.g. https://<resource>.openai.azure.com
    azure_deployment: str | None = None     # deployment / model name in Azure
    azure_api_version: str = "2024-02-01"
    # OpenAI-compatible base URL (leave None for official OpenAI)
    base_url: str | None = None


class ConnectionUpdate(BaseModel):
    name: str | None = None
    api_key: str | None = None
    azure_endpoint: str | None = None
    azure_deployment: str | None = None
    azure_api_version: str | None = None
    base_url: str | None = None


class ConnectionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    type: ConnectionType
    api_key_hint: str       # last 4 chars only
    azure_endpoint: str | None
    azure_deployment: str | None
    azure_api_version: str
    base_url: str | None
    created_at: datetime


# ---------------------------------------------------------------------------
# Playground
# ---------------------------------------------------------------------------

class McpToolSchema(BaseModel):
    name: str
    description: str
    parameters: dict


class McpServerCreate(BaseModel):
    name: str
    url: str
    token: str | None = None           # plain Bearer token; encrypted before storing
    oauth_client_id: str | None = None
    oauth_client_secret: str | None = None  # plain; encrypted before storing
    skip_verify: bool = False          # skip connection verification (used for OAuth flow)


class McpServerUpdate(BaseModel):
    name: str | None = None
    url: str | None = None
    token: str | None = None
    oauth_client_id: str | None = None
    oauth_client_secret: str | None = None
    skip_verify: bool = False


class McpServerSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    url: str
    has_token: bool = False
    has_oauth: bool = False         # True if OAuth client credentials configured
    oauth_connected: bool = False   # True if access token stored
    oauth_client_id: str | None = None  # exposed for editing (not sensitive)
    created_at: datetime


class OAuthStartRequest(BaseModel):
    redirect_uri: str
    scope: str | None = None


class OAuthStartResponse(BaseModel):
    authorization_url: str
    state: str


class OAuthCallbackRequest(BaseModel):
    code: str
    state: str
    redirect_uri: str


class SingleRunRequest(BaseModel):
    prompt_id: str
    input: str = ""
    variables: dict[str, str] = Field(default_factory=dict)
    connection_id: str | None = None
    max_output_tokens: int | None = None
    use_responses_api: bool | None = None
    mcp_server_id: str | None = None
    mcp_tool_filter: list[str] | None = None  # null = all tools


class SingleRunResult(BaseModel):
    output: str
    raw_output: Any = None
    tool_calls: list[dict] | None = Field(default=None)


class ScorerRunRequest(BaseModel):
    scorer_id: str
    input: str = ""
    output: str = ""
    variables: dict[str, str] = Field(default_factory=dict)
    connection_id: str | None = None


class ScorerRunResult(BaseModel):
    score: str


class RowRunRequest(BaseModel):
    row_id: str
    input: str
    comment: str = ""
    prompt_id: str
    scorer_id: str
    prompt_version_id: str | None = None
    prompt_connection_id: str | None = None
    scorer_connection_id: str | None = None
    max_output_tokens: int | None = None
    mcp_server_id: str | None = None
    mcp_tool_filter: list[str] | None = None


class PlaygroundRunRequest(BaseModel):
    prompt_id: str
    dataset_id: str
    scorer_id: str
    prompt_version_id: str | None = None
    prompt_connection_id: str | None = None
    scorer_connection_id: str | None = None
    max_output_tokens: int | None = None
    mcp_server_id: str | None = None
    mcp_tool_filter: list[str] | None = None


class RowEvalResult(BaseModel):
    row_id: str
    input: str
    comment: str
    output: str           # LLM response for the prompt
    score: str            # Scorer LLM response
    error: str | None = None
    elapsed_ms: int | None = None
    tool_calls: list[dict] | None = Field(default=None)


class PlaygroundRunResult(BaseModel):
    prompt_id: str
    dataset_id: str
    scorer_id: str
    results: list[RowEvalResult]


# ---------------------------------------------------------------------------
# Playground (saved configurations + run history)
# ---------------------------------------------------------------------------

class PlaygroundCreate(BaseModel):
    name: str
    prompt_id: str | None = None
    dataset_id: str | None = None
    scorer_id: str | None = None
    prompt_connection_id: str | None = None
    scorer_connection_id: str | None = None
    mcp_server_id: str | None = None
    mcp_tool_filter: list[str] | None = None


class PlaygroundUpdate(BaseModel):
    name: str | None = None
    prompt_id: str | None = None
    dataset_id: str | None = None
    scorer_id: str | None = None
    prompt_connection_id: str | None = None
    scorer_connection_id: str | None = None
    mcp_server_id: str | None = None
    mcp_tool_filter: list[str] | None = None


class PlaygroundRunRowSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    row_id: str
    input: str
    comment: str
    output: str
    score: str
    error: str | None = None
    elapsed_ms: int | None = None
    tool_calls: list[dict] | None = Field(default=None)


class PlaygroundRunSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    playground_id: str
    created_at: datetime
    prompt_version_id: str | None = None
    prompt_version_number: int | None = None
    prompt_id: str | None = None
    dataset_id: str | None = None
    scorer_id: str | None = None
    rows: list[PlaygroundRunRowSchema] = Field(default_factory=list)


class PlaygroundSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    prompt_id: str | None
    dataset_id: str | None
    scorer_id: str | None
    prompt_connection_id: str | None
    scorer_connection_id: str | None
    mcp_server_id: str | None = None
    mcp_tool_filter: list[str] | None = None
    created_at: datetime
    created_by_email: str | None = None
    runs: list[PlaygroundRunSchema] = Field(default_factory=list)


class SaveRunRequest(BaseModel):
    rows: list[RowEvalResult]
    prompt_version_id: str | None = None
    prompt_version_number: int | None = None
    prompt_id: str | None = None
    dataset_id: str | None = None
    scorer_id: str | None = None


# ---------------------------------------------------------------------------
# Reviews
# ---------------------------------------------------------------------------

class ReviewRowSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    review_id: str
    input: str
    output: str
    score: str
    row_comment: str
    prompt_string: str | None = None
    annotation: str | None = None
    rating: str | None = None  # good | bad | neutral
    expected_behavior: str | None = None
    created_at: datetime


class ReviewSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    playground_id: str | None = None
    playground_name: str | None = None
    run_label: str | None = None
    source: str = "playground"
    agent_chat_id: str | None = None
    created_at: datetime
    rows: list[ReviewRowSchema] = Field(default_factory=list)


class ReviewCreateRow(BaseModel):
    input: str
    output: str
    score: str = ""
    row_comment: str = ""
    prompt_string: str | None = None


class ReviewCreate(BaseModel):
    name: str
    playground_id: str | None = None
    playground_name: str | None = None
    run_label: str | None = None
    source: str = "playground"
    agent_chat_id: str | None = None
    rows: list[ReviewCreateRow] = Field(default_factory=list)


class ReviewRowUpdate(BaseModel):
    annotation: str | None = None
    rating: str | None = None
    expected_behavior: str | None = None


# ---------------------------------------------------------------------------
# Agents
# ---------------------------------------------------------------------------

class AgentCreate(BaseModel):
    name: str
    system_prompt: str = ""
    connection_id: str | None = None
    model: str | None = None
    max_output_tokens: int | None = None
    mcp_server_id: str | None = None
    mcp_tool_filter: list[str] | None = None
    tools: list[str] = Field(default_factory=list)
    summarize_after: int = Field(default=10, ge=2, le=20)
    use_responses_api: bool = False

    @field_validator("summarize_after")
    @classmethod
    def clamp_summarize_after(cls, v: int) -> int:
        return max(2, min(20, v))


class AgentUpdate(BaseModel):
    name: str | None = None
    system_prompt: str | None = None
    connection_id: str | None = None
    model: str | None = None
    max_output_tokens: int | None = None
    mcp_server_id: str | None = None
    mcp_tool_filter: list[str] | None = None
    tools: list[str] | None = None
    summarize_after: int | None = Field(default=None, ge=2, le=20)
    use_responses_api: bool | None = None

    @field_validator("summarize_after")
    @classmethod
    def clamp_summarize_after(cls, v: int | None) -> int | None:
        if v is None:
            return v
        return max(2, min(20, v))


class AgentSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    system_prompt: str
    connection_id: str | None = None
    model: str | None = None
    max_output_tokens: int | None = None
    mcp_server_id: str | None = None
    mcp_tool_filter: list[str] | None = None
    tools: list[str]
    summarize_after: int
    use_responses_api: bool
    created_at: datetime
    created_by_email: str | None = None


class AgentMessageSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    chat_id: str
    role: str  # user | assistant
    content: str
    tool_calls: list[dict] | None = None
    created_at: datetime


class AgentChatSummarySchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    chat_id: str
    content: str
    from_message_id: str | None = None
    to_message_id: str | None = None
    created_at: datetime


class AgentChatSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    agent_id: str
    created_at: datetime
    messages: list[AgentMessageSchema] = Field(default_factory=list)
    summaries: list[AgentChatSummarySchema] = Field(default_factory=list)


class AgentSendMessageRequest(BaseModel):
    content: str
