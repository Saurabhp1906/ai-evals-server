import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from .routers import prompts, datasets, scorers, playground, playgrounds, connections, organizations, invites, mcp_servers

_ALLOWED_ORIGINS = [
    o.strip()
    for o in os.environ.get("ALLOWED_ORIGINS", "http://localhost:5173,http://localhost:3000").split(",")
    if o.strip()
]

app = FastAPI(
    title="AI Evals Server",
    description="An AI evaluation platform",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=_ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(organizations.router)
app.include_router(invites.router)
app.include_router(connections.router)
app.include_router(prompts.router)
app.include_router(datasets.router)
app.include_router(scorers.router)
app.include_router(playground.router)
app.include_router(playgrounds.router)
app.include_router(mcp_servers.router)



@app.get("/", tags=["health"])
def health() -> dict:
    return {"status": "ok"}


def main() -> None:
    import uvicorn
    from .database.migrations import run_migrations

    print("Running database migrations...")
    run_migrations()
    print("Migrations complete, starting server...")

    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", 8000)))


if __name__ == "__main__":
    main()
