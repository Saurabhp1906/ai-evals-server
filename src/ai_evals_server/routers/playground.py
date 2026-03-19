import json
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


def _serialize_response(response: object) -> dict:
    """Serialize an SDK response object to a plain JSON-compatible dict."""
    errors: list[str] = []
    # Pydantic v2 — JSON-safe dict
    try:
        return response.model_dump(mode="json")  # type: ignore[attr-defined]
    except Exception as e:
        errors.append(f"model_dump: {e}")
    # Pydantic v2 — via JSON string
    try:
        return json.loads(response.model_dump_json())  # type: ignore[attr-defined]
    except Exception as e:
        errors.append(f"model_dump_json: {e}")
    # Pydantic v1
    try:
        return json.loads(response.json())  # type: ignore[attr-defined]
    except Exception as e:
        errors.append(f"json(): {e}")
    # __dict__ fallback
    try:
        return json.loads(json.dumps(response.__dict__, default=str))
    except Exception as e:
        errors.append(f"__dict__: {e}")
    # vars() fallback
    try:
        return json.loads(json.dumps(vars(response), default=str))
    except Exception as e:
        errors.append(f"vars(): {e}")
    return {"_error": "could not serialize response", "_details": errors}

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
    def complete(self, model: str, user_message: str, max_tokens: int | None = None, tools: list[str] | None = None) -> str: ...


class ClaudeClient:
    def __init__(self, api_key: str) -> None:
        self._client = anthropic.Anthropic(api_key=api_key)

    def complete(self, model: str, user_message: str, max_tokens: int | None = None, tools: list[str] | None = None) -> str:
        kwargs: dict = {
            "model": model,
            "max_tokens": max_tokens if max_tokens is not None else 1024,
            "messages": [{"role": "user", "content": user_message}],
        }
        tool_defs = [CLAUDE_TOOL_DEFINITIONS[t] for t in (tools or []) if t in CLAUDE_TOOL_DEFINITIONS]
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
        text = "\n".join(parts).strip()
        return text

    def complete_raw(self, model: str, user_message: str, max_tokens: int | None, tools: list[str]) -> tuple[str, dict]:
        kwargs: dict = {
            "model": model,
            "max_tokens": max_tokens if max_tokens is not None else 1024,
            "messages": [{"role": "user", "content": user_message}],
        }
        tool_defs = [CLAUDE_TOOL_DEFINITIONS[t] for t in (tools or []) if t in CLAUDE_TOOL_DEFINITIONS]
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
        return "\n".join(parts).strip(), _serialize_response(response)


def _openai_chat_create(client, kwargs: dict, max_tokens: int | None):
    """Call chat.completions.create, falling back to max_completion_tokens if max_tokens is rejected."""
    if max_tokens is not None:
        kwargs["max_tokens"] = max_tokens
    try:
        return client.chat.completions.create(**kwargs)
    except openai_lib.BadRequestError as e:
        if max_tokens is not None and "max_completion_tokens" in str(e):
            kwargs.pop("max_tokens", None)
            kwargs["max_completion_tokens"] = max_tokens
            return client.chat.completions.create(**kwargs)
        raise


class OpenAIChatClient:
    """OpenAI Chat Completions API — available on all plans."""
    def __init__(self, api_key: str, base_url: str | None = None) -> None:
        self._client = openai_lib.OpenAI(api_key=api_key, base_url=base_url)

    def complete(self, model: str, user_message: str, max_tokens: int | None = None, tools: list[str] | None = None) -> str:
        kwargs: dict = {
            "model": model,
            "messages": [{"role": "user", "content": user_message}],
        }
        # web_search not supported in Chat Completions — ignore tools silently
        response = _openai_chat_create(self._client, kwargs, max_tokens)
        return (response.choices[0].message.content or "").strip()

    def complete_raw(self, model: str, user_message: str, max_tokens: int | None, tools: list[str]) -> tuple[str, dict]:
        kwargs: dict = {
            "model": model,
            "messages": [{"role": "user", "content": user_message}],
        }
        response = _openai_chat_create(self._client, kwargs, max_tokens)
        return (response.choices[0].message.content or "").strip(), _serialize_response(response)


class OpenAIResponsesClient:
    """OpenAI Responses API — Plus/Pro plans only."""
    def __init__(self, api_key: str, base_url: str | None = None) -> None:
        self._client = openai_lib.OpenAI(api_key=api_key, base_url=base_url)

    def complete(self, model: str, user_message: str, max_tokens: int | None = None, tools: list[str] | None = None) -> str:
        kwargs: dict = {
            "model": model,
            "input": user_message,
        }
        if max_tokens is not None:
            kwargs["max_output_tokens"] = max_tokens
        tool_defs = [OPENAI_TOOL_DEFINITIONS[t] for t in (tools or []) if t in OPENAI_TOOL_DEFINITIONS]
        if tool_defs:
            kwargs["tools"] = tool_defs
            kwargs["tool_choice"] = "required"
        response = self._client.responses.create(**kwargs)
        return (response.output_text or "").strip()

    def complete_raw(self, model: str, user_message: str, max_tokens: int | None, tools: list[str]) -> tuple[str, dict]:
        kwargs: dict = {"model": model, "input": user_message}
        if max_tokens is not None:
            kwargs["max_output_tokens"] = max_tokens
        tool_defs = [OPENAI_TOOL_DEFINITIONS[t] for t in (tools or []) if t in OPENAI_TOOL_DEFINITIONS]
        if tool_defs:
            kwargs["tools"] = tool_defs
            kwargs["tool_choice"] = "required"
        response = self._client.responses.create(**kwargs)
        return (response.output_text or "").strip(), _serialize_response(response)


class AzureOpenAIChatClient:
    """Azure OpenAI Chat Completions API."""
    def __init__(self, api_key: str, azure_endpoint: str, azure_deployment: str, api_version: str) -> None:
        self._client = openai_lib.AzureOpenAI(
            api_key=api_key,
            azure_endpoint=azure_endpoint,
            api_version=api_version,
        )
        self._deployment = azure_deployment

    def complete(self, model: str, user_message: str, max_tokens: int | None = None, tools: list[str] | None = None) -> str:
        kwargs: dict = {
            "model": self._deployment,
            "messages": [{"role": "user", "content": user_message}],
        }
        response = _openai_chat_create(self._client, kwargs, max_tokens)
        return (response.choices[0].message.content or "").strip()

    def complete_raw(self, model: str, user_message: str, max_tokens: int | None, tools: list[str]) -> tuple[str, dict]:
        kwargs: dict = {"model": self._deployment, "messages": [{"role": "user", "content": user_message}]}
        response = _openai_chat_create(self._client, kwargs, max_tokens)
        return (response.choices[0].message.content or "").strip(), _serialize_response(response)


class AzureOpenAIResponsesClient:
    """Azure OpenAI Responses API."""
    def __init__(self, api_key: str, azure_endpoint: str, azure_deployment: str, api_version: str) -> None:
        self._client = openai_lib.AzureOpenAI(
            api_key=api_key,
            azure_endpoint=azure_endpoint,
            api_version=api_version,
        )
        self._deployment = azure_deployment

    def complete(self, model: str, user_message: str, max_tokens: int | None = None, tools: list[str] | None = None) -> str:
        kwargs: dict = {
            "model": self._deployment,
            "input": user_message,
        }
        if max_tokens is not None:
            kwargs["max_output_tokens"] = max_tokens
        tool_defs = [OPENAI_TOOL_DEFINITIONS[t] for t in (tools or []) if t in OPENAI_TOOL_DEFINITIONS]
        if tool_defs:
            kwargs["tools"] = tool_defs
            kwargs["tool_choice"] = "required"
        response = self._client.responses.create(**kwargs)
        return (response.output_text or "").strip()

    def complete_raw(self, model: str, user_message: str, max_tokens: int | None, tools: list[str]) -> tuple[str, dict]:
        kwargs: dict = {"model": self._deployment, "input": user_message}
        if max_tokens is not None:
            kwargs["max_output_tokens"] = max_tokens
        tool_defs = [OPENAI_TOOL_DEFINITIONS[t] for t in (tools or []) if t in OPENAI_TOOL_DEFINITIONS]
        if tool_defs:
            kwargs["tools"] = tool_defs
            kwargs["tool_choice"] = "required"
        response = self._client.responses.create(**kwargs)
        return (response.output_text or "").strip(), _serialize_response(response)


# ---------------------------------------------------------------------------
# Client factory
# ---------------------------------------------------------------------------

def _client_from_connection(
    conn: ConnectionORM,
    use_responses_api: bool | None = None,
) -> ClaudeClient | OpenAIChatClient | OpenAIResponsesClient | AzureOpenAIChatClient | AzureOpenAIResponsesClient:
    plain_key = decrypt_api_key(conn.api_key)
    if conn.type == ConnectionType.claude:
        return ClaudeClient(api_key=plain_key)
    if conn.type in (ConnectionType.openai, ConnectionType.openai_responses):
        # Default based on connection type; override if explicitly requested
        responses = (conn.type == ConnectionType.openai_responses) if use_responses_api is None else use_responses_api
        if responses:
            return OpenAIResponsesClient(api_key=plain_key, base_url=conn.base_url)
        return OpenAIChatClient(api_key=plain_key, base_url=conn.base_url)
    # azure_openai — default chat completions; override to responses if requested
    responses = False if use_responses_api is None else use_responses_api
    azure_kwargs = dict(
        api_key=plain_key,
        azure_endpoint=conn.azure_endpoint or "",
        azure_deployment=conn.azure_deployment or "",
        api_version=conn.azure_api_version,
    )
    if responses:
        return AzureOpenAIResponsesClient(**azure_kwargs)
    return AzureOpenAIChatClient(**azure_kwargs)


def _resolve_client(connection_id: str | None, db: Session, use_responses_api: bool | None = None):
    if not connection_id:
        raise HTTPException(status_code=400, detail="A connection must be selected to run.")
    conn = db.get(ConnectionORM, connection_id)
    if not conn:
        raise HTTPException(status_code=404, detail=f"Connection '{connection_id}' not found")
    return _client_from_connection(conn, use_responses_api=use_responses_api)


_DEFAULT_MODELS = {
    ConnectionType.claude: "claude-sonnet-4-6",
    ConnectionType.openai: "gpt-4o",
    ConnectionType.openai_responses: "gpt-4o",
    ConnectionType.azure_openai: "",
}


def _resolve_model(connection_id: str | None, db: Session) -> str:
    if not connection_id:
        raise HTTPException(status_code=400, detail="A connection must be selected to run.")
    conn = db.get(ConnectionORM, connection_id)
    if not conn:
        raise HTTPException(status_code=404, detail=f"Connection '{connection_id}' not found")
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
    use_responses_api = body.use_responses_api if body.use_responses_api is not None else prompt.use_responses_api
    client = _resolve_client(connection_id, db, use_responses_api=use_responses_api)
    model = _resolve_model(connection_id, db)
    max_tokens = body.max_output_tokens or prompt.max_output_tokens
    user_message = _resolve_template(prompt.prompt_string, body.input, body.variables)

    try:
        output, raw_output = client.complete_raw(model=model, user_message=user_message, max_tokens=max_tokens, tools=prompt.tools)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))

    return SingleRunResult(output=output, raw_output=raw_output)


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
        score = client.complete(model=model, user_message=scorer_message)
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
    scorer_connection_id = body.scorer_connection_id or prompt_connection_id
    prompt_client = _resolve_client(prompt_connection_id, db, use_responses_api=prompt.use_responses_api)
    scorer_client = _resolve_client(scorer_connection_id, db)
    prompt_model = _resolve_model(prompt_connection_id, db)
    scorer_model = _resolve_model(scorer_connection_id, db)

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
        score = scorer_client.complete(model=scorer_model, user_message=scorer_message)
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
    scorer_connection_id = body.scorer_connection_id or prompt_connection_id
    prompt_client = _resolve_client(prompt_connection_id, db, use_responses_api=prompt.use_responses_api)
    scorer_client = _resolve_client(scorer_connection_id, db)
    prompt_model = _resolve_model(prompt_connection_id, db)
    scorer_model = _resolve_model(scorer_connection_id, db)

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
