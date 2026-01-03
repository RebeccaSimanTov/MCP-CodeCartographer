from __future__ import annotations
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any


class MetaModel(BaseModel):
    request_id: Optional[str] = None
    duration_seconds: Optional[float] = None
    extra: Optional[Dict[str, Any]] = None


class ErrorModel(BaseModel):
    code: Optional[str] = None
    message: str


class ScanResult(BaseModel):
    analyzed_files: int
    most_central: str
    path: str
    success: bool = True
    meta: Optional[Dict[str, Any]] = None
    errors: List[ErrorModel] = Field(default_factory=list)
    # Serialized graph so callers can use it directly (nodes with attrs and edge pairs)
    graph: Optional[Dict[str, Any]] = None
    # Identifier of the persisted graph file (saved under <scan_path>/graphs/<graph_id>.json)
    graph_id: Optional[str] = None


class MapResult(BaseModel):
    success: bool = True
    node_count: int = 0
    edge_count: int = 0
    message: Optional[str] = None
    image_filename: Optional[str] = None
    image_path: Optional[str] = None
    meta: Optional[Dict[str, Any]] = None
    errors: List[ErrorModel] = Field(default_factory=list)


class AIAnalysis(BaseModel):
    module: str
    dependencies: List[str] = Field(default_factory=list)
    used_by: List[str] = Field(default_factory=list)
    analysis: str
    simulated: bool = False
    meta: Optional[Dict[str, Any]] = None
    errors: List[ErrorModel] = Field(default_factory=list)
