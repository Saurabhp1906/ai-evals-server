from datetime import datetime
from enum import Enum
from typing import Any
from pydantic import BaseModel, ConfigDict, Field


# ---------------------------------------------------------------------------
# Prompt
# ---------------------------------------------------------------------------

class PromptCreate(BaseModel):
    name: str
    prompt_string: str  # use {input} or ${varName} as placeholders
    tools: list[str] = Field(default_factory=list)  # e.g. ["web_search"]
    use_responses_api: bool = False
    connection_id: str | None = None
    max_output_tokens: int | None = None
    model: str | None = None  # optional model override (used for OpenAI connections)


class PromptUpdate(BaseModel):
    name: str | None = None
    prompt_string: str | None = None
    tools: list[str] | None = None
    use_responses_api: bool | None = None
    connection_id: str | None = None
    max_output_tokens: int | None = None
    model: str | None = None


class Prompt(PromptCreate):
    model_config = ConfigDict(from_attributes=True)

    id: str
    created_at: datetime


class PromptVersionCreate(BaseModel):
    prompt_string: str
    version_number: int


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

class SingleRunRequest(BaseModel):
    prompt_id: str
    input: str = ""
    variables: dict[str, str] = Field(default_factory=dict)
    connection_id: str | None = None
    max_output_tokens: int | None = None
    use_responses_api: bool | None = None  # if None, falls back to prompt.use_responses_api


class SingleRunResult(BaseModel):
    output: str
    raw_output: Any = None


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
    prompt_connection_id: str | None = None
    scorer_connection_id: str | None = None
    max_output_tokens: int | None = None


class PlaygroundRunRequest(BaseModel):
    prompt_id: str
    dataset_id: str
    scorer_id: str
    prompt_connection_id: str | None = None
    scorer_connection_id: str | None = None
    max_output_tokens: int | None = None


class RowEvalResult(BaseModel):
    row_id: str
    input: str
    comment: str
    output: str           # LLM response for the prompt
    score: str            # Scorer LLM response
    error: str | None = None
    elapsed_ms: int | None = None


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


class PlaygroundUpdate(BaseModel):
    name: str | None = None
    prompt_id: str | None = None
    dataset_id: str | None = None
    scorer_id: str | None = None
    prompt_connection_id: str | None = None
    scorer_connection_id: str | None = None


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


class PlaygroundRunSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    playground_id: str
    created_at: datetime
    prompt_version_id: str | None = None
    prompt_version_number: int | None = None
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
    created_at: datetime
    runs: list[PlaygroundRunSchema] = Field(default_factory=list)


class SaveRunRequest(BaseModel):
    rows: list[RowEvalResult]
    prompt_version_id: str | None = None
    prompt_version_number: int | None = None
