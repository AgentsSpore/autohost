from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


class NodeType(str, Enum):
    http_request = "http_request"
    transform = "transform"
    log = "log"
    delay = "delay"


class Node(BaseModel):
    id: str
    type: NodeType
    config: dict = {}


class Edge(BaseModel):
    source: str
    target: str


class WorkflowCreate(BaseModel):
    name: str = Field(max_length=100)
    nodes: list[Node]
    edges: list[Edge] = []


class WorkflowResponse(BaseModel):
    id: int
    name: str
    nodes: list[Node]
    edges: list[Edge]
    created_at: str


class RunResponse(BaseModel):
    id: int
    workflow_id: int
    status: str
    logs: list[str]
    started_at: str
    finished_at: str | None = None
