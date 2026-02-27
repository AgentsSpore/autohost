from __future__ import annotations

import asyncio
import json
from collections import defaultdict, deque
from datetime import datetime, timezone

import aiosqlite

SQL_TABLES = """
CREATE TABLE IF NOT EXISTS workflows (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    nodes TEXT NOT NULL,
    edges TEXT NOT NULL DEFAULT '[]',
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    workflow_id INTEGER NOT NULL,
    status TEXT NOT NULL DEFAULT 'running',
    logs TEXT NOT NULL DEFAULT '[]',
    started_at TEXT NOT NULL,
    finished_at TEXT,
    FOREIGN KEY (workflow_id) REFERENCES workflows(id)
);
"""


async def init_db(path: str) -> aiosqlite.Connection:
    db = await aiosqlite.connect(path)
    db.row_factory = aiosqlite.Row
    await db.executescript(SQL_TABLES)
    await db.commit()
    return db


def topological_sort(nodes: list[dict], edges: list[dict]) -> list[str]:
    """Kahn's algorithm — returns node IDs in execution order."""
    graph: dict[str, list[str]] = defaultdict(list)
    in_degree: dict[str, int] = {n["id"]: 0 for n in nodes}

    for e in edges:
        graph[e["source"]].append(e["target"])
        in_degree[e["target"]] = in_degree.get(e["target"], 0) + 1

    queue = deque(nid for nid, deg in in_degree.items() if deg == 0)
    order: list[str] = []

    while queue:
        nid = queue.popleft()
        order.append(nid)
        for neighbor in graph[nid]:
            in_degree[neighbor] -= 1
            if in_degree[neighbor] == 0:
                queue.append(neighbor)

    return order


async def execute_node(node: dict, context: dict) -> str:
    """Run a single node and return a log line."""
    ntype = node["type"]
    cfg = node.get("config", {})
    nid = node["id"]

    if ntype == "http_request":
        url = cfg.get("url", "https://example.com")
        method = cfg.get("method", "GET")
        context["last_response"] = {"status": 200, "body": f"Mock response from {url}"}
        return f"[http_request:{nid}] {method} {url} -> 200 OK"

    if ntype == "transform":
        expr = cfg.get("expression", "passthrough")
        data = str(context.get("last_response", ""))
        if ".upper()" in expr:
            result = data.upper()
        elif ".lower()" in expr:
            result = data.lower()
        else:
            result = data
        context["last_transform"] = result
        return f"[transform:{nid}] Applied '{expr}' -> {result[:80]}"

    if ntype == "log":
        msg = cfg.get("message", "")
        return f"[log:{nid}] {msg}"

    if ntype == "delay":
        secs = min(cfg.get("seconds", 1), 5)
        await asyncio.sleep(secs)
        return f"[delay:{nid}] Waited {secs}s"

    return f"[unknown:{nid}] Skipped"


async def run_workflow(db: aiosqlite.Connection, workflow_id: int) -> int:
    """Execute a workflow in background. Returns run ID."""
    rows = await db.execute_fetchall("SELECT * FROM workflows WHERE id = ?", (workflow_id,))
    if not rows:
        raise ValueError(f"Workflow {workflow_id} not found")

    wf = dict(rows[0])
    nodes = json.loads(wf["nodes"])
    edges = json.loads(wf["edges"])

    now = datetime.now(timezone.utc).isoformat()
    cur = await db.execute(
        "INSERT INTO runs (workflow_id, status, started_at) VALUES (?, 'running', ?)",
        (workflow_id, now),
    )
    await db.commit()
    run_id = cur.lastrowid

    logs: list[str] = []
    context: dict = {}
    status = "completed"

    try:
        order = topological_sort(nodes, edges)
        node_map = {n["id"]: n for n in nodes}

        for nid in order:
            node = node_map.get(nid)
            if not node:
                continue
            log_line = await execute_node(node, context)
            logs.append(log_line)
    except Exception as exc:
        logs.append(f"[error] {exc}")
        status = "failed"

    finished = datetime.now(timezone.utc).isoformat()
    await db.execute(
        "UPDATE runs SET status = ?, logs = ?, finished_at = ? WHERE id = ?",
        (status, json.dumps(logs), finished, run_id),
    )
    await db.commit()
    return run_id


async def list_workflows(db: aiosqlite.Connection) -> list[dict]:
    rows = await db.execute_fetchall("SELECT * FROM workflows ORDER BY created_at DESC")
    result = []
    for r in rows:
        d = dict(r)
        d["nodes"] = json.loads(d["nodes"])
        d["edges"] = json.loads(d["edges"])
        result.append(d)
    return result


async def get_workflow(db: aiosqlite.Connection, wf_id: int) -> dict | None:
    rows = await db.execute_fetchall("SELECT * FROM workflows WHERE id = ?", (wf_id,))
    if not rows:
        return None
    d = dict(rows[0])
    d["nodes"] = json.loads(d["nodes"])
    d["edges"] = json.loads(d["edges"])
    return d


async def get_run(db: aiosqlite.Connection, run_id: int) -> dict | None:
    rows = await db.execute_fetchall("SELECT * FROM runs WHERE id = ?", (run_id,))
    if not rows:
        return None
    d = dict(rows[0])
    d["logs"] = json.loads(d["logs"])
    return d
