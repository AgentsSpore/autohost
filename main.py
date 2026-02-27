from __future__ import annotations

import json
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import BackgroundTasks, FastAPI, HTTPException

from engine import init_db, run_workflow, list_workflows, get_workflow, get_run
from models import WorkflowCreate, WorkflowResponse, RunResponse

DB_PATH = "autohost.db"


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.db = await init_db(DB_PATH)
    yield
    await app.state.db.close()


app = FastAPI(
    title="AutoHost",
    description="One-click self-hosted automation builder — define workflows, run with one command",
    version="0.1.0",
    lifespan=lifespan,
)


@app.post("/workflows", response_model=WorkflowResponse)
async def create(body: WorkflowCreate):
    db = app.state.db
    now = datetime.now(timezone.utc).isoformat()
    nodes_json = json.dumps([n.model_dump() for n in body.nodes])
    edges_json = json.dumps([e.model_dump() for e in body.edges])

    cur = await db.execute(
        "INSERT INTO workflows (name, nodes, edges, created_at) VALUES (?, ?, ?, ?)",
        (body.name, nodes_json, edges_json, now),
    )
    await db.commit()
    wf = await get_workflow(db, cur.lastrowid)
    return wf


@app.get("/workflows", response_model=list[WorkflowResponse])
async def index():
    return await list_workflows(app.state.db)


@app.post("/workflows/{workflow_id}/run", response_model=RunResponse)
async def start_run(workflow_id: int, bg: BackgroundTasks):
    wf = await get_workflow(app.state.db, workflow_id)
    if not wf:
        raise HTTPException(404, "Workflow not found")

    run_id = await run_workflow(app.state.db, workflow_id)
    run = await get_run(app.state.db, run_id)
    return run


@app.get("/runs/{run_id}", response_model=RunResponse)
async def show_run(run_id: int):
    run = await get_run(app.state.db, run_id)
    if not run:
        raise HTTPException(404, "Run not found")
    return run
