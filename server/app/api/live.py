"""Live measurement WebSocket: desktop publisher and browser viewer fan-out."""

from __future__ import annotations

import asyncio

import jwt
from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect
from sqlalchemy.orm import Session

from server.app.api.deps import get_configured_api_key
from server.app.db.session import get_db
from server.app.models.account_models import AccountRecord
from server.app.services.auth_service import get_configured_jwt_secret
from server.app.services.live_hub import LiveHub
from server.app.services.people_service import list_linked_students

router = APIRouter(tags=["live"])
hub = LiveHub()


def _account_from_token(db: Session, token: str) -> AccountRecord | None:
    if not token:
        return None
    try:
        payload = jwt.decode(token, get_configured_jwt_secret(), algorithms=["HS256"])
    except jwt.InvalidTokenError:
        return None
    account_id = payload.get("acc") or (payload.get("sub") if payload.get("typ") == "account" else None)
    if not account_id:
        return None
    return db.get(AccountRecord, str(account_id))


async def _send_json(websocket: WebSocket, frame: dict) -> None:
    try:
        await websocket.send_json(frame)
    except Exception:
        return


def _make_send(websocket: WebSocket):
    def send(frame: dict) -> None:
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return
        loop.create_task(_send_json(websocket, frame))

    return send


async def _close(websocket: WebSocket, code: int) -> None:
    try:
        await websocket.close(code=code)
    except Exception:
        return


@router.websocket("/live/ws")
async def live_ws(websocket: WebSocket, db: Session = Depends(get_db)) -> None:
    await websocket.accept()
    cookie = websocket.cookies.get("apl_web_token")
    account = _account_from_token(db, cookie) if cookie else None
    kind = "viewer"
    if account is None:
        try:
            raw = await websocket.receive_json()
        except WebSocketDisconnect:
            await _close(websocket, 4401)
            return
        if not isinstance(raw, dict) or raw.get("type") != "auth" or not raw.get("token"):
            await _close(websocket, 4401)
            return
        if raw.get("api_key") != get_configured_api_key():
            await _close(websocket, 4401)
            return
        account = _account_from_token(db, str(raw["token"]))
        kind = "desktop"
    if account is None or not account.role:
        await _close(websocket, 4403)
        return
    send = _make_send(websocket)
    viewer_id = f"{account.id}:view:{id(websocket)}"
    watch = frozenset({account.id})
    if kind == "viewer" and account.role == "teacher":
        watch = frozenset(row.id for row in list_linked_students(db, account))
    try:
        if kind == "desktop":
            hub.set_publisher(account.id, send)
        else:
            hub.add_viewer(viewer_id, watch, send)
            for student_id in watch:
                for frame in hub.buffer_for(student_id):
                    await websocket.send_json(frame)
        await websocket.send_json({"type": "hello", "role": account.role})
        while True:
            message = await websocket.receive_json()
            if not isinstance(message, dict):
                continue
            mtype = message.get("type")
            if mtype == "ping":
                await websocket.send_json({"type": "pong"})
            elif mtype == "auth":
                if message.get("api_key") != get_configured_api_key() or not message.get("token"):
                    continue
                auth_account = _account_from_token(db, str(message["token"]))
                if auth_account is None or not auth_account.role:
                    continue
                if kind == "viewer":
                    hub.remove_viewer(viewer_id)
                kind = "desktop"
                account = auth_account
                hub.set_publisher(account.id, send)
            elif mtype == "samples" and kind == "desktop":
                points = message.get("points") or []
                if not isinstance(points, list):
                    continue
                hub.publish_samples(
                    account.id,
                    experiment_id=str(message.get("experiment_id") or ""),
                    session_id=str(message.get("session_id") or ""),
                    points=points[:50],
                )
            elif mtype == "status" and kind == "desktop":
                hub.publish_status(
                    account.id,
                    state=str(message.get("state") or "idle"),
                    experiment_id=str(message.get("experiment_id") or ""),
                )
            elif mtype == "command":
                continue
    except WebSocketDisconnect:
        pass
    finally:
        if kind == "desktop":
            hub.clear_publisher_if(account.id, send)
        else:
            hub.remove_viewer(viewer_id)
