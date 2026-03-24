import json

import anthropic
import openai as openai_lib
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..auth.dependencies import CurrentUser, get_current_user
from ..auth.limits import check_daily_quota
from ..auth.utils import decrypt_api_key
from ..database import get_db
from ..models.orm import ConnectionORM, DatasetORM, PromptORM, ScorerORM
from ..models.schemas import (
    ConnectionType,
    PlaygroundRunRequest, PlaygroundRunResult,
    RowEvalResult, RowRunRequest,
    ScorerRunRequest, ScorerRunResult,
    SingleRunRequest, SingleRunResult,
)
from .llm_clients import resolve_client, resolve_model
from .mcp_utils import resolve_mcp, run_with_mcp

router = APIRouter(prefix="/playground", tags=["playground"])


# ---------------------------------------------------------------------------
# Scorer — forced tool call → structured {"score": int, "reasoning": str}
# ---------------------------------------------------------------------------

_SUBMIT_SCORE_TOOL_CLAUDE = {
    "name": "submit_score",
    "description": "Submit the evaluation score and reasoning for the given output",
    "input_schema": {
        "type": "object",
        "properties": {
            "score": {"type": "integer", "minimum": 0, "maximum": 10, "description": "Integer score from 0 to 10"},
            "reasoning": {"type": "string", "description": "Explanation for the score"},
        },
        "required": ["score", "reasoning"],
    },
}

_SUBMIT_SCORE_TOOL_OPENAI = {
    "type": "function",
    "function": {
        "name": "submit_score",
        "description": "Submit the evaluation score and reasoning for the given output",
        "parameters": {
            "type": "object",
            "properties": {
                "score": {"type": "integer", "minimum": 0, "maximum": 10, "description": "Integer score from 0 to 10"},
                "reasoning": {"type": "string", "description": "Explanation for the score"},
            },
            "required": ["score", "reasoning"],
        },
    },
}


def _run_scorer(conn: ConnectionORM, model: str, scorer_message: str) -> str:
    """Run scorer via forced tool call. Returns JSON: {"score": int, "reasoning": str}."""
    plain_key = decrypt_api_key(conn.api_key)

    if conn.type == ConnectionType.claude:
        client = anthropic.Anthropic(api_key=plain_key)
        response = client.messages.create(
            model=model,
            max_tokens=512,
            messages=[{"role": "user", "content": scorer_message}],
            tools=[_SUBMIT_SCORE_TOOL_CLAUDE],
            tool_choice={"type": "tool", "name": "submit_score"},
        )
        for block in response.content:
            if hasattr(block, "type") and block.type == "tool_use" and block.name == "submit_score":
                args = block.input
                return json.dumps({"score": int(args["score"]), "reasoning": str(args.get("reasoning", ""))})
        raise ValueError("submit_score tool was not called")

    if conn.type == ConnectionType.openai:
        openai_client: openai_lib.OpenAI | openai_lib.AzureOpenAI = openai_lib.OpenAI(api_key=plain_key, base_url=conn.base_url)
        deployment = model
    else:
        openai_client = openai_lib.AzureOpenAI(
            api_key=plain_key,
            azure_endpoint=conn.azure_endpoint or "",
            api_version=conn.azure_api_version,
        )
        deployment = conn.azure_deployment or model

    kwargs: dict = {
        "model": deployment,
        "messages": [{"role": "user", "content": scorer_message}],
        "tools": [_SUBMIT_SCORE_TOOL_OPENAI],
        "tool_choice": {"type": "function", "function": {"name": "submit_score"}},
    }
    try:
        response = openai_client.chat.completions.create(**kwargs)
    except openai_lib.BadRequestError as e:
        if "max_completion_tokens" in str(e):
            kwargs["max_completion_tokens"] = 512
            response = openai_client.chat.completions.create(**kwargs)
        else:
            raise
    tc = response.choices[0].message.tool_calls[0]
    args = json.loads(tc.function.arguments)
    return json.dumps({"score": int(args["score"]), "reasoning": str(args.get("reasoning", ""))})


# ---------------------------------------------------------------------------
# Prompt / template helpers
# ---------------------------------------------------------------------------

def _get_prompt_string(prompt: PromptORM, version_id: str | None = None) -> str:
    if not prompt.versions:
        raise HTTPException(status_code=400, detail=f"Prompt '{prompt.id}' has no versions")
    if version_id:
        v = next((v for v in prompt.versions if v.id == version_id), None)
        if not v:
            raise HTTPException(status_code=404, detail=f"Version '{version_id}' not found on prompt '{prompt.id}'")
        return v.prompt_string
    return max(prompt.versions, key=lambda v: v.version_number).prompt_string


def _parse_variables(input_str: str) -> tuple[dict[str, str], str]:
    try:
        parsed = json.loads(input_str)
        if isinstance(parsed, dict):
            return {k: str(v) for k, v in parsed.items()}, input_str
    except (json.JSONDecodeError, ValueError):
        pass
    return {}, input_str


_RESERVED = {"input", "output"}


def _resolve_template(template: str, input_str: str, variables: dict[str, str], output: str = "") -> str:
    result = template
    for key, value in variables.items():
        result = result.replace(f"${{{key}}}", value)
    result = result.replace("{input}", input_str)
    result = result.replace("{output}", output)
    for key, value in variables.items():
        if key not in _RESERVED:
            result = result.replace(f"{{{key}}}", value)
    return result


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.post("/run-single", response_model=SingleRunResult)
def run_single(
    body: SingleRunRequest,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> SingleRunResult:
    check_daily_quota(
        db, current_user.org_id, current_user.org_plan, "playground_runs",
        increment=1, custom_limits=current_user.org_custom_limits,
    )
    prompt = db.get(PromptORM, body.prompt_id)
    if not prompt:
        raise HTTPException(status_code=404, detail="Prompt not found")

    connection_id = body.connection_id or prompt.connection_id
    use_responses_api = body.use_responses_api if body.use_responses_api is not None else prompt.use_responses_api
    max_tokens = body.max_output_tokens or prompt.max_output_tokens
    user_message = _resolve_template(_get_prompt_string(prompt), body.input, body.variables)

    mcp_url, mcp_headers = resolve_mcp(body.mcp_server_id, db)
    tool_calls: list[dict] = []
    try:
        if mcp_url:
            if not connection_id:
                raise HTTPException(status_code=400, detail="A connection must be selected to run.")
            conn = db.get(ConnectionORM, connection_id)
            if not conn:
                raise HTTPException(status_code=404, detail="Connection not found")
            output, tool_calls, raw_output = run_with_mcp(conn, user_message, max_tokens, mcp_url, mcp_headers, body.mcp_tool_filter, use_responses_api=use_responses_api, model=prompt.model, prompt_tools=prompt.tools)
        else:
            client = resolve_client(connection_id, db, use_responses_api=use_responses_api)
            model = resolve_model(connection_id, db, model_override=prompt.model)
            output, raw_output = client.complete_raw(model=model, user_message=user_message, max_tokens=max_tokens, tools=prompt.tools, response_format=prompt.response_format)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))

    return SingleRunResult(output=output, raw_output=raw_output, tool_calls=tool_calls)


@router.post("/run-scorer", response_model=ScorerRunResult)
def run_scorer(
    body: ScorerRunRequest,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> ScorerRunResult:
    check_daily_quota(
        db, current_user.org_id, current_user.org_plan, "scorer_evaluations",
        increment=1, custom_limits=current_user.org_custom_limits,
    )
    scorer = db.get(ScorerORM, body.scorer_id)
    if not scorer:
        raise HTTPException(status_code=404, detail="Scorer not found")

    connection_id = body.connection_id or scorer.connection_id
    if not connection_id:
        raise HTTPException(status_code=400, detail="A connection must be selected to run.")
    conn = db.get(ConnectionORM, connection_id)
    if not conn:
        raise HTTPException(status_code=404, detail="Connection not found")
    model = resolve_model(connection_id, db)
    scorer_message = _resolve_template(scorer.prompt_string, body.input, body.variables, output=body.output)

    try:
        score = _run_scorer(conn, model, scorer_message)
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
    scorer_connection_id = body.scorer_connection_id or scorer.connection_id or prompt_connection_id
    prompt_client = resolve_client(prompt_connection_id, db, use_responses_api=prompt.use_responses_api)
    prompt_model = resolve_model(prompt_connection_id, db, model_override=prompt.model)
    scorer_model = resolve_model(scorer_connection_id, db)
    scorer_conn = db.get(ConnectionORM, scorer_connection_id)
    if not scorer_conn:
        raise HTTPException(status_code=404, detail="Scorer connection not found")

    mcp_url, mcp_headers = resolve_mcp(body.mcp_server_id, db)
    output = ""
    score = ""
    error = None
    tool_calls: list[dict] = []
    try:
        variables, raw_input = _parse_variables(body.input)
        max_tokens = body.max_output_tokens or prompt.max_output_tokens
        user_message = _resolve_template(_get_prompt_string(prompt, body.prompt_version_id), raw_input, variables)

        if mcp_url:
            prompt_conn = db.get(ConnectionORM, prompt_connection_id)
            if not prompt_conn:
                raise HTTPException(status_code=404, detail="Prompt connection not found")
            output, tool_calls, _ = run_with_mcp(prompt_conn, user_message, max_tokens, mcp_url, mcp_headers, body.mcp_tool_filter, use_responses_api=prompt.use_responses_api, model=prompt.model, prompt_tools=prompt.tools)
        else:
            output = prompt_client.complete(model=prompt_model, user_message=user_message, max_tokens=max_tokens, tools=prompt.tools, response_format=prompt.response_format)

        scorer_message = _resolve_template(scorer.prompt_string, raw_input, variables, output=output)
        score = _run_scorer(scorer_conn, scorer_model, scorer_message)
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
        tool_calls=tool_calls,
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

    row_count = len(dataset.rows)
    check_daily_quota(db, current_user.org_id, current_user.org_plan, "playground_runs", increment=row_count, custom_limits=current_user.org_custom_limits)
    check_daily_quota(db, current_user.org_id, current_user.org_plan, "scorer_evaluations", increment=row_count, custom_limits=current_user.org_custom_limits)

    prompt_connection_id = body.prompt_connection_id or prompt.connection_id
    scorer_connection_id = body.scorer_connection_id or scorer.connection_id or prompt_connection_id
    prompt_client = resolve_client(prompt_connection_id, db, use_responses_api=prompt.use_responses_api)
    prompt_model = resolve_model(prompt_connection_id, db, model_override=prompt.model)
    scorer_model = resolve_model(scorer_connection_id, db)
    scorer_conn = db.get(ConnectionORM, scorer_connection_id)
    if not scorer_conn:
        raise HTTPException(status_code=404, detail="Scorer connection not found")

    mcp_url, mcp_headers = resolve_mcp(body.mcp_server_id, db)
    prompt_conn = db.get(ConnectionORM, prompt_connection_id) if mcp_url else None

    results: list[RowEvalResult] = []
    for row in dataset.rows:
        output = ""
        score = ""
        error = None
        tool_calls: list[dict] = []
        try:
            variables, raw_input = _parse_variables(row.input)
            max_tokens = body.max_output_tokens or prompt.max_output_tokens
            user_message = _resolve_template(_get_prompt_string(prompt, body.prompt_version_id), raw_input, variables)

            if mcp_url:
                if not prompt_conn:
                    raise HTTPException(status_code=404, detail="Prompt connection not found")
                output, tool_calls, _ = run_with_mcp(prompt_conn, user_message, max_tokens, mcp_url, mcp_headers, body.mcp_tool_filter, use_responses_api=prompt.use_responses_api, model=prompt.model, prompt_tools=prompt.tools)
            else:
                output = prompt_client.complete(model=prompt_model, user_message=user_message, max_tokens=max_tokens, tools=prompt.tools, response_format=prompt.response_format)

            scorer_message = _resolve_template(scorer.prompt_string, raw_input, variables, output=output)
            score = _run_scorer(scorer_conn, scorer_model, scorer_message)
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
            tool_calls=tool_calls,
        ))

    return PlaygroundRunResult(
        prompt_id=body.prompt_id,
        dataset_id=body.dataset_id,
        scorer_id=body.scorer_id,
        results=results,
    )
