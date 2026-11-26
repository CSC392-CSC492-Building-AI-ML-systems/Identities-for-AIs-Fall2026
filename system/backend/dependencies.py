"""FastAPI dependency wiring. Override for tests; later inject real services."""
from __future__ import annotations

from fastapi import Request
from .services.analysis import MockAnalysisGateway


def get_analysis_gateway(request: Request) -> MockAnalysisGateway:
    return request.app.state.analysis_gateway


def get_live_analysis_gateway(request: Request):
    """Injectable live-target analysis service (credentials never in app.state)."""
    return request.app.state.live_analysis_gateway
