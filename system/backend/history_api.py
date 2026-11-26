"""Authenticated deployment history and read-only authoritative repository cards."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request

from .security.auth import require_user
from .history_store import NotFound
from .history_schemas import DeploymentCreate, ManualBaselineCreate
from .cards_repository import CardsUnavailable

router = APIRouter(prefix='/api/v1', tags=['Model cards and monitored deployments'])


def owned_store(request: Request):
    return request.app.state.history_store


def _known_model(request: Request, model_id: str) -> None:
    if not request.app.state.catalog.has(model_id):
        raise HTTPException(status_code=404, detail='Unknown catalog model ID')


def _get_card(request: Request, model_id: str):
    try:
        return request.app.state.repository_cards.get(model_id)
    except (CardsUnavailable, OSError, ValueError):
        return None


@router.get('/models/{model_id}/card')
def get_model_card(model_id: str, request: Request, user: str = Depends(require_user)):
    _known_model(request, model_id)
    card = _get_card(request, model_id)
    return {'model_id': model_id, 'status': 'available' if card else 'unavailable',
            'card': card, 'note': 'Card availability is not fingerprint identity confirmation'}


@router.post('/deployments', status_code=201)
def create_deployment(body: DeploymentCreate, request: Request, user: str = Depends(require_user)):
    return owned_store(request).create_deployment(user, body.label, body.provider, body.requested_model_id)


@router.get('/deployments')
def list_deployments(request: Request, user: str = Depends(require_user)):
    return {'deployments': owned_store(request).list_deployments(user)}


@router.get('/deployments/{deployment_id}')
def get_deployment(deployment_id: str, request: Request, user: str = Depends(require_user)):
    try:
        return owned_store(request).get_deployment(user, deployment_id)
    except NotFound:
        raise HTTPException(status_code=404, detail='Deployment not found') from None


@router.post('/deployments/{deployment_id}/baselines', status_code=201)
def record_baseline(deployment_id: str, body: ManualBaselineCreate,
                    request: Request, user: str = Depends(require_user)):
    _known_model(request, body.model_id)
    card = _get_card(request, body.model_id)
    try:
        return owned_store(request).record_reviewed_baseline(user, deployment_id,
            body.model_id, body.review_note, card)
    except NotFound:
        raise HTTPException(status_code=404, detail='Deployment not found') from None


@router.get('/deployments/{deployment_id}/history')
def get_history(deployment_id: str, request: Request, user: str = Depends(require_user)):
    try:
        return {'deployment_id': deployment_id,
                'history': owned_store(request).list_history(user, deployment_id)}
    except NotFound:
        raise HTTPException(status_code=404, detail='Deployment not found') from None


@router.get('/deployments/{deployment_id}/changes')
def get_changes(deployment_id: str, request: Request, user: str = Depends(require_user)):
    try:
        data = owned_store(request).changes(user, deployment_id)
    except NotFound:
        raise HTTPException(status_code=404, detail='Deployment not found') from None
    old, new = data.get('before_model_id'), data.get('after_model_id')
    data['before_family_id'] = request.app.state.catalog.get(old).family_id if old else None
    data['after_family_id'] = request.app.state.catalog.get(new).family_id if new else None
    data['family_change'] = (data['before_family_id'] != data['after_family_id']
                             if old and new else None)
    data['deployment_id'] = deployment_id
    data['evidence_status'] = 'manual_reviewed_history_only'
    return data
