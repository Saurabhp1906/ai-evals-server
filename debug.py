"""
debug.py — interactive debug shell for ai-evals-server.

Run with:
    python debug.py

Gives you a live DB session, all ORM models, and helper functions
pre-imported so you can inspect or mutate data without starting the server.
"""

import os
import sys

# Make sure the src package is importable when running from the project root.
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

from dotenv import load_dotenv
load_dotenv()

from ai_evals_server.database.session import SessionLocal
from ai_evals_server.models.orm import (
    ConnectionORM,
    DatasetORM,
    DatasetRowORM,
    PromptORM,
    ScorerORM,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

db = SessionLocal()


def connections():
    return db.query(ConnectionORM).all()


def prompts():
    return db.query(PromptORM).all()


def datasets():
    return db.query(DatasetORM).all()


def scorers():
    return db.query(ScorerORM).all()


def rows(dataset_id: str):
    return db.query(DatasetRowORM).filter(DatasetRowORM.dataset_id == dataset_id).all()


def get(model, id: str):
    return db.get(model, id)


def delete(obj):
    db.delete(obj)
    db.commit()
    print(f"Deleted {obj}")


def test_connection(connection_id: str):
    """Verify a saved connection actually works by sending a minimal request."""
    from ai_evals_server.routers.playground import _client_from_connection, _resolve_model
    conn = db.get(ConnectionORM, connection_id)
    if not conn:
        print(f"No connection with id {connection_id!r}")
        return
    client = _client_from_connection(conn)
    model = _resolve_model(connection_id, conn.azure_deployment or "gpt-4o-mini", db)
    try:
        out = client.complete(model=model, user_message="Say hello.", max_tokens=16, tools=[])
        print(f"OK — response: {out!r}")
    except Exception as e:
        print(f"FAILED — {e}")


def run_prompt(prompt_id: str, input_text: str, connection_id: str | None = None):
    """Run a single prompt against an input string and print the output."""
    from ai_evals_server.routers.playground import _resolve_client, _resolve_model
    prompt = db.get(PromptORM, prompt_id)
    if not prompt:
        print(f"No prompt with id {prompt_id!r}")
        return
    client = _resolve_client(connection_id, db)
    model = _resolve_model(connection_id, prompt.model, db)
    message = prompt.prompt_string.replace("{input}", input_text)
    try:
        out = client.complete(model=model, user_message=message, max_tokens=2048, tools=prompt.tools)
        print(out)
    except Exception as e:
        print(f"FAILED — {e}")


# ---------------------------------------------------------------------------
# Banner
# ---------------------------------------------------------------------------

print("AI Evals debug shell")
print(f"  DB: {os.environ.get('DATABASE_URL', 'postgresql://postgres:postgres@localhost:5432/ai_evals')}")
print()
print("Available:")
print("  connections()                          list all connections")
print("  prompts()                              list all prompts")
print("  datasets()                             list all datasets")
print("  scorers()                              list all scorers")
print("  rows(dataset_id)                       list rows for a dataset")
print("  get(ModelClass, id)                    fetch one record")
print("  delete(obj)                            delete a record")
print("  test_connection(connection_id)         verify a connection works")
print("  run_prompt(prompt_id, input, conn_id)  run a prompt and print output")
print("  db                                     raw SQLAlchemy session")
print()

# Drop into an interactive REPL with everything in scope.
import code
code.interact(local={**globals(), **locals()}, banner="")
