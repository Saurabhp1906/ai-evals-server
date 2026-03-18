import json
import os
from typing import Protocol
from fastapi import APIRouter, Depends, HTTPException
import anthropic
import openai as openai_lib
from sqlalchemy.orm import Session

from ..auth.dependencies import CurrentUser, get_current_user
from ..auth.utils import decrypt_api_key
from ..database import get_db
from ..models.orm import ConnectionORM, DatasetORM, PromptORM, ScorerORM
from ..models.schemas import ConnectionType, PlaygroundRunRequest, PlaygroundRunResult, RowEvalResult, RowRunRequest, ScorerRunRequest, ScorerRunResult, SingleRunRequest, SingleRunResult

router = APIRouter(prefix="/playground", tags=["playground"])

# ---------------------------------------------------------------------------
# Tool definitions (Claude-native built-ins)
# ---------------------------------------------------------------------------

CLAUDE_TOOL_DEFINITIONS: dict[str, dict] = {
    "web_search": {
        "type": "web_search_20250305",
        "name": "web_search",
    },
}

OPENAI_TOOL_DEFINITIONS: dict[str, dict] = {
    "web_search": {
        "type": "web_search",
    },
}


# ---------------------------------------------------------------------------
# Unified LLM client abstraction
# ---------------------------------------------------------------------------

class LLMClient(Protocol):
    def complete(self, model: str, user_message: str, max_tokens: int | None, tools: list[str]) -> str: ...


class ClaudeClient:
    def __init__(self, api_key: str) -> None:
        self._client = anthropic.Anthropic(api_key=api_key)

    def complete(self, model: str, user_message: str, max_tokens: int | None, tools: list[str]) -> str:
        kwargs: dict = {
            "model": model,
            "max_tokens": max_tokens if max_tokens is not None else 1024,
            "messages": [{"role": "user", "content": user_message}],
        }
        tool_defs = [CLAUDE_TOOL_DEFINITIONS[t] for t in tools if t in CLAUDE_TOOL_DEFINITIONS]
        if tool_defs:
            kwargs["tools"] = tool_defs
            kwargs["tool_choice"] = {"type": "required"}

        response = self._client.messages.create(**kwargs)
        parts = []
        for block in response.content:
            if hasattr(block, "text"):
                parts.append(block.text)
            elif isinstance(block, dict) and block.get("type") == "text":
                parts.append(block["text"])
        return "\n".join(parts).strip()


class OpenAIClient:
    def __init__(self, api_key: str, base_url: str | None = None) -> None:
        self._client = openai_lib.OpenAI(api_key=api_key, base_url=base_url)

    def complete(self, model: str, user_message: str, max_tokens: int | None, tools: list[str]) -> str:
        kwargs: dict = {
            "model": model,
            "input": user_message,
        }
        if max_tokens is not None:
            kwargs["max_output_tokens"] = max_tokens
        tool_defs = [OPENAI_TOOL_DEFINITIONS[t] for t in tools if t in OPENAI_TOOL_DEFINITIONS]
        if tool_defs:
            kwargs["tools"] = tool_defs
            kwargs["tool_choice"] = "required"
        response = self._client.responses.create(**kwargs)
        return (response.output_text or "").strip()


class AzureOpenAIClient:
    def __init__(self, api_key: str, azure_endpoint: str, azure_deployment: str, api_version: str) -> None:
        self._client = openai_lib.AzureOpenAI(
            api_key=api_key,
            azure_endpoint=azure_endpoint,
            api_version=api_version,
        )
        self._deployment = azure_deployment

    def complete(self, model: str, user_message: str, max_tokens: int | None, tools: list[str]) -> str:
        kwargs: dict = {
            "model": self._deployment,
            "input": user_message,
        }
        if max_tokens is not None:
            kwargs["max_output_tokens"] = max_tokens
        tool_defs = [OPENAI_TOOL_DEFINITIONS[t] for t in tools if t in OPENAI_TOOL_DEFINITIONS]
        if tool_defs:
            kwargs["tools"] = tool_defs
            kwargs["tool_choice"] = "required"
        response = self._client.responses.create(**kwargs)
        return (response.output_text or "").strip()


# ---------------------------------------------------------------------------
# Client factory
# ---------------------------------------------------------------------------

def _client_from_connection(conn: ConnectionORM) -> ClaudeClient | OpenAIClient | AzureOpenAIClient:
    plain_key = decrypt_api_key(conn.api_key)
    if conn.type == ConnectionType.claude:
        return ClaudeClient(api_key=plain_key)
    if conn.type == ConnectionType.openai:
        return OpenAIClient(api_key=plain_key, base_url=conn.base_url)
    return AzureOpenAIClient(
        api_key=plain_key,
        azure_endpoint=conn.azure_endpoint or "",
        azure_deployment=conn.azure_deployment or "",
        api_version=conn.azure_api_version,
    )


def _default_claude_client() -> ClaudeClient:
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise HTTPException(
            status_code=500,
            detail="No connection specified and ANTHROPIC_API_KEY env var is not set",
        )
    return ClaudeClient(api_key=api_key)


def _resolve_client(connection_id: str | None, db: Session) -> ClaudeClient | OpenAIClient | AzureOpenAIClient:
    if not connection_id:
        return _default_claude_client()
    conn = db.get(ConnectionORM, connection_id)
    if not conn:
        raise HTTPException(status_code=404, detail=f"Connection '{connection_id}' not found")
    return _client_from_connection(conn)


_DEFAULT_MODELS = {
    ConnectionType.claude: "claude-sonnet-4-6",
    ConnectionType.openai: "gpt-4o",
    ConnectionType.azure_openai: "",
}


def _resolve_model(connection_id: str | None, db: Session) -> str:
    if not connection_id:
        return _DEFAULT_MODELS[ConnectionType.claude]
    conn = db.get(ConnectionORM, connection_id)
    if not conn:
        return _DEFAULT_MODELS[ConnectionType.claude]
    if conn.type == ConnectionType.azure_openai and conn.azure_deployment:
        return conn.azure_deployment
    return _DEFAULT_MODELS.get(conn.type, "claude-sonnet-4-6")


# ---------------------------------------------------------------------------
# Template resolution
# ---------------------------------------------------------------------------

def _parse_variables(input_str: str) -> tuple[dict[str, str], str]:
    """Parse input_str as JSON variables if possible. Returns (variables, raw_input)."""
    try:
        parsed = json.loads(input_str)
        if isinstance(parsed, dict):
            return {k: str(v) for k, v in parsed.items()}, input_str
    except (json.JSONDecodeError, ValueError):
        pass
    return {}, input_str


_RESERVED = {"input", "output"}


def _resolve_template(template: str, input_str: str, variables: dict[str, str], output: str = "") -> str:
    """Substitute {input}, {output}, ${varName}, and {varName} placeholders in a template."""
    result = template
    for key, value in variables.items():
        result = result.replace(f"${{{key}}}", value)
    result = result.replace("{input}", input_str)
    result = result.replace("{output}", output)
    # Also support bare {varName} for non-reserved keys
    for key, value in variables.items():
        if key not in _RESERVED:
            result = result.replace(f"{{{key}}}", value)
    return result


# ---------------------------------------------------------------------------
# Playground endpoint
# ---------------------------------------------------------------------------

@router.post("/run-single", response_model=SingleRunResult)
def run_single(
    body: SingleRunRequest,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> SingleRunResult:
    prompt = db.get(PromptORM, body.prompt_id)
    if not prompt:
        raise HTTPException(status_code=404, detail="Prompt not found")

    connection_id = body.connection_id or prompt.connection_id
    client = _resolve_client(connection_id, db)
    model = _resolve_model(connection_id, db)
    max_tokens = body.max_output_tokens or prompt.max_output_tokens
    user_message = _resolve_template(prompt.prompt_string, body.input, body.variables)

    try:
        output = client.complete(model=model, user_message=user_message, max_tokens=max_tokens, tools=prompt.tools)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))

    return SingleRunResult(output=output)


@router.post("/run-scorer", response_model=ScorerRunResult)
def run_scorer(
    body: ScorerRunRequest,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> ScorerRunResult:
    scorer = db.get(ScorerORM, body.scorer_id)
    if not scorer:
        raise HTTPException(status_code=404, detail="Scorer not found")

    client = _resolve_client(body.connection_id, db)
    model = _resolve_model(body.connection_id, db)
    scorer_message = _resolve_template(scorer.prompt_string, body.input, body.variables, output=body.output)

    try:
        score = client.complete(model=model, user_message=scorer_message, max_tokens=1024, tools=[])
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))

    return ScorerRunResult(score=score)


@router.post("/run-row", response_model=RowEvalResult)
def run_row(
    body: RowRunRequest,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> RowEvalResult:
    prompt = db.get(PromptORM, body.prompt_id)
    if not prompt:
        raise HTTPException(status_code=404, detail="Prompt not found")

    scorer = db.get(ScorerORM, body.scorer_id)
    if not scorer:
        raise HTTPException(status_code=404, detail="Scorer not found")

    prompt_connection_id = body.prompt_connection_id or prompt.connection_id
    prompt_client = _resolve_client(prompt_connection_id, db)
    scorer_client = _resolve_client(body.scorer_connection_id, db)
    prompt_model = _resolve_model(prompt_connection_id, db)
    scorer_model = _resolve_model(body.scorer_connection_id, db)

    output = ""
    score = ""
    error = None
    try:
        variables, raw_input = _parse_variables(body.input)
        max_tokens = body.max_output_tokens or prompt.max_output_tokens

        user_message = _resolve_template(prompt.prompt_string, raw_input, variables)
        output = prompt_client.complete(
            model=prompt_model,
            user_message=user_message,
            max_tokens=max_tokens,
            tools=prompt.tools,
        )

        scorer_message = _resolve_template(scorer.prompt_string, raw_input, variables, output=output)
        score = scorer_client.complete(
            model=scorer_model,
            user_message=scorer_message,
            max_tokens=1024,
            tools=[],
        )
    except HTTPException:
        raise
    except Exception as exc:
        error = str(exc)

    return RowEvalResult(
        row_id=body.row_id,
        input=body.input,
        comment=body.comment,
        output=output,
        score=score,
        error=error,
    )


@router.post("/run", response_model=PlaygroundRunResult)
def run_playground(
    body: PlaygroundRunRequest,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> PlaygroundRunResult:
    prompt = db.get(PromptORM, body.prompt_id)
    if not prompt:
        raise HTTPException(status_code=404, detail="Prompt not found")

    dataset = db.get(DatasetORM, body.dataset_id)
    if not dataset:
        raise HTTPException(status_code=404, detail="Dataset not found")

    scorer = db.get(ScorerORM, body.scorer_id)
    if not scorer:
        raise HTTPException(status_code=404, detail="Scorer not found")

    if not dataset.rows:
        raise HTTPException(status_code=400, detail="Dataset has no rows")

    prompt_connection_id = body.prompt_connection_id or prompt.connection_id
    prompt_client = _resolve_client(prompt_connection_id, db)
    scorer_client = _resolve_client(body.scorer_connection_id, db)
    prompt_model = _resolve_model(prompt_connection_id, db)
    scorer_model = _resolve_model(body.scorer_connection_id, db)

    results: list[RowEvalResult] = []

    for row in dataset.rows:
        output = ""
        score = ""
        error = None
        try:
            variables, raw_input = _parse_variables(row.input)
            max_tokens = body.max_output_tokens or prompt.max_output_tokens

            user_message = _resolve_template(prompt.prompt_string, raw_input, variables)
            output = prompt_client.complete(
                model=prompt_model,
                user_message=user_message,
                max_tokens=max_tokens,
                tools=prompt.tools,
            )

            scorer_message = _resolve_template(scorer.prompt_string, raw_input, variables, output=output)
            score = scorer_client.complete(
                model=scorer_model,
                user_message=scorer_message,
                max_tokens=1024,
                tools=[],
            )
        except HTTPException:
            raise
        except Exception as exc:
            error = str(exc)

        results.append(RowEvalResult(
            row_id=row.id,
            input=row.input,
            comment=row.comment,
            output=output,
            score=score,
            error=error,
        ))

    return PlaygroundRunResult(
        prompt_id=body.prompt_id,
        dataset_id=body.dataset_id,
        scorer_id=body.scorer_id,
        results=results,
    )
