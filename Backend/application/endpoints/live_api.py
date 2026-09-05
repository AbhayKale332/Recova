"""HTTP API for the single-worker interactive recovery theatre."""

from __future__ import annotations

import asyncio
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field, model_validator
from sqlalchemy.orm import Session

from application.endpoints.stream_api import _SSE_HEADERS, _sse
from application.persistence import get_db
from application.operations.live_session import create_session, get_session, remove_session


router = APIRouter(prefix="/live/sessions", tags=["live"])


class CreateSessionBody(BaseModel):
    custom_case: dict[str, Any] | None = None
    transaction_id: str | None = None
    locale: str = "en"

    @model_validator(mode="after")
    def _one_source(self) -> "CreateSessionBody":
        if (self.custom_case is None) == (self.transaction_id is None):
            raise ValueError("provide exactly one of custom_case or transaction_id")
        return self


class ReplyBody(BaseModel):
    text: str = Field(min_length=1, max_length=2000)


class TurnBody(BaseModel):
    speaker: str
    text: str = Field(min_length=1, max_length=5000)
    at_offset_sec: int = Field(0, ge=0)


def _require(session_id: str):
    session = get_session(session_id)
    if session is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Live session not found")
    return session


@router.post("", status_code=status.HTTP_201_CREATED)
def create_live_session(payload: CreateSessionBody, db: Session = Depends(get_db)) -> dict[str, str]:
    try:
        session = create_session(
            db,
            custom_case=payload.custom_case,
            transaction_id=payload.transaction_id,
            locale=payload.locale,
        )
    except LookupError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Transaction not found")
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))
    return {"session_id": session.session_id, "transaction_id": session.transaction_id}


@router.get("/{session_id}/stream")
def stream_live_session(session_id: str, db: Session = Depends(get_db)) -> StreamingResponse:
    session = _require(session_id)
    session.start(db)

    async def event_stream():
        session.bind_loop(asyncio.get_running_loop())
        while True:
            item = await session.queue.get()
            if item is None:
                return
            event, data = item
            yield _sse(event, data)

    return StreamingResponse(event_stream(), media_type="text/event-stream", headers=_SSE_HEADERS)


@router.post("/{session_id}/reply")
def reply_live_session(session_id: str, payload: ReplyBody, db: Session = Depends(get_db)) -> dict[str, Any]:
    session = _require(session_id)
    return session.reply(db, payload.text)


@router.post("/{session_id}/call/web")
def web_call_config(session_id: str, db: Session = Depends(get_db)) -> dict[str, Any]:
    session = _require(session_id)
    try:
        return session.call_web(db)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))


@router.post("/{session_id}/turns")
def ingest_call_turn(session_id: str, payload: TurnBody, db: Session = Depends(get_db)) -> dict[str, Any]:
    session = _require(session_id)
    try:
        return session.ingest_turn(db, payload.speaker, payload.text, payload.at_offset_sec)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))


@router.delete("/{session_id}")
def delete_live_session(session_id: str, db: Session = Depends(get_db)) -> dict[str, Any]:
    session = _require(session_id)
    session.close(db)
    remove_session(session_id)
    return {"session_id": session_id, "deleted": True}
