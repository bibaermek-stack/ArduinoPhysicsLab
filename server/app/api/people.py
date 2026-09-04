"""People search and relationship request routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from server.app.api.deps import get_current_account, require_api_key
from server.app.db.session import get_db
from server.app.models.account_models import AccountRecord
from server.app.schemas.account import (
    ConnectTeacherBody,
    PersonSummary,
    RequestListResponse,
    RequestSummary,
    SearchResponse,
    SendRequestBody,
)
from server.app.services.account_service import AccountError, encode_photo_base64
from server.app.services.people_service import (
    KIND_FRIEND,
    KIND_TEACHER_STUDENT,
    accept_request,
    connect_to_teacher,
    decline_request,
    get_by_public_id,
    list_requests,
    search_people,
    search_teachers,
    send_request,
)

router = APIRouter(tags=["people"], dependencies=[Depends(require_api_key)])


def _summary(account: AccountRecord, include_photo: bool = False) -> PersonSummary:
    return PersonSummary(
        account_id=account.id,
        public_id=account.public_id or "",
        display_name=account.display_name,
        role=account.role or "",
        photo_base64=encode_photo_base64(account.photo_bytes) if include_photo else None,
    )


@router.get("/teachers/search", response_model=SearchResponse)
def teachers_search(
    query: str = Query(default="", min_length=0, alias="query"),
    db: Session = Depends(get_db),
    account: AccountRecord = Depends(get_current_account),
) -> SearchResponse:
    del account
    rows = search_teachers(db, query)
    return SearchResponse(results=[_summary(row) for row in rows if row.public_id])


@router.post("/student/connect-teacher", response_model=RequestSummary)
def student_connect_teacher(
    body: ConnectTeacherBody,
    db: Session = Depends(get_db),
    account: AccountRecord = Depends(get_current_account),
) -> RequestSummary:
    try:
        row = connect_to_teacher(db, account, body.resolved_code())
    except AccountError as error:
        code = status.HTTP_404_NOT_FOUND if "табылмады" in str(error) else status.HTTP_400_BAD_REQUEST
        raise HTTPException(status_code=code, detail=str(error)) from None
    db.commit()
    from_acc = db.get(AccountRecord, row.from_account_id)
    to_acc = db.get(AccountRecord, row.to_account_id)
    return RequestSummary(
        id=row.id,
        kind=row.kind,
        from_public_id=from_acc.public_id or "" if from_acc else "",
        from_display_name=from_acc.display_name if from_acc else "",
        to_public_id=to_acc.public_id or "" if to_acc else "",
        to_display_name=to_acc.display_name if to_acc else "",
        status=row.status,
        direction="outgoing",
    )


@router.get("/people/search", response_model=SearchResponse)
def people_search(
    q: str = Query(default="", min_length=0),
    db: Session = Depends(get_db),
    account: AccountRecord = Depends(get_current_account),
) -> SearchResponse:
    del account
    rows = search_people(db, q)
    return SearchResponse(results=[_summary(row) for row in rows if row.public_id])


@router.get("/people/{public_id}", response_model=PersonSummary)
def people_get(
    public_id: str,
    db: Session = Depends(get_db),
    account: AccountRecord = Depends(get_current_account),
) -> PersonSummary:
    del account
    try:
        row = get_by_public_id(db, public_id)
    except AccountError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error)) from None
    return _summary(row, include_photo=True)


@router.post("/requests/teacher-student", response_model=RequestSummary)
def post_teacher_student_request(
    body: SendRequestBody,
    db: Session = Depends(get_db),
    account: AccountRecord = Depends(get_current_account),
) -> RequestSummary:
    try:
        row = send_request(db, account, body.to_public_id, KIND_TEACHER_STUDENT)
    except AccountError as error:
        raise HTTPException(status_code=400, detail=str(error)) from None
    db.commit()
    from_acc = db.get(AccountRecord, row.from_account_id)
    to_acc = db.get(AccountRecord, row.to_account_id)
    return RequestSummary(
        id=row.id,
        kind=row.kind,
        from_public_id=from_acc.public_id or "",
        from_display_name=from_acc.display_name if from_acc else "",
        to_public_id=to_acc.public_id or "",
        to_display_name=to_acc.display_name if to_acc else "",
        status=row.status,
        direction="outgoing",
    )


@router.post("/requests/friends", response_model=RequestSummary)
def post_friend_request(
    body: SendRequestBody,
    db: Session = Depends(get_db),
    account: AccountRecord = Depends(get_current_account),
) -> RequestSummary:
    try:
        row = send_request(db, account, body.to_public_id, KIND_FRIEND)
    except AccountError as error:
        raise HTTPException(status_code=400, detail=str(error)) from None
    db.commit()
    from_acc = db.get(AccountRecord, row.from_account_id)
    to_acc = db.get(AccountRecord, row.to_account_id)
    return RequestSummary(
        id=row.id,
        kind=row.kind,
        from_public_id=from_acc.public_id or "",
        from_display_name=from_acc.display_name if from_acc else "",
        to_public_id=to_acc.public_id or "",
        to_display_name=to_acc.display_name if to_acc else "",
        status=row.status,
        direction="outgoing",
    )


@router.get("/requests/incoming", response_model=RequestListResponse)
def incoming_requests(
    db: Session = Depends(get_db),
    account: AccountRecord = Depends(get_current_account),
) -> RequestListResponse:
    items = []
    for row, from_acc, to_acc in list_requests(db, account):
        items.append(
            RequestSummary(
                id=row.id,
                kind=row.kind,
                from_public_id=from_acc.public_id or "",
                from_display_name=from_acc.display_name,
                to_public_id=to_acc.public_id or "",
                to_display_name=to_acc.display_name,
                status=row.status,
                direction="incoming" if row.to_account_id == account.id else "outgoing",
            )
        )
    return RequestListResponse(items=items)


@router.post("/requests/{request_id}/accept", response_model=RequestSummary)
def accept(
    request_id: str,
    db: Session = Depends(get_db),
    account: AccountRecord = Depends(get_current_account),
) -> RequestSummary:
    try:
        row = accept_request(db, account, request_id)
    except AccountError as error:
        raise HTTPException(status_code=400, detail=str(error)) from None
    db.commit()
    from_acc = db.get(AccountRecord, row.from_account_id)
    to_acc = db.get(AccountRecord, row.to_account_id)
    return RequestSummary(
        id=row.id,
        kind=row.kind,
        from_public_id=from_acc.public_id or "" if from_acc else "",
        from_display_name=from_acc.display_name if from_acc else "",
        to_public_id=to_acc.public_id or "" if to_acc else "",
        to_display_name=to_acc.display_name if to_acc else "",
        status=row.status,
        direction="incoming",
    )


@router.post("/requests/{request_id}/decline", response_model=RequestSummary)
def decline(
    request_id: str,
    db: Session = Depends(get_db),
    account: AccountRecord = Depends(get_current_account),
) -> RequestSummary:
    try:
        row = decline_request(db, account, request_id)
    except AccountError as error:
        raise HTTPException(status_code=400, detail=str(error)) from None
    db.commit()
    from_acc = db.get(AccountRecord, row.from_account_id)
    to_acc = db.get(AccountRecord, row.to_account_id)
    return RequestSummary(
        id=row.id,
        kind=row.kind,
        from_public_id=from_acc.public_id or "" if from_acc else "",
        from_display_name=from_acc.display_name if from_acc else "",
        to_public_id=to_acc.public_id or "" if to_acc else "",
        to_display_name=to_acc.display_name if to_acc else "",
        status=row.status,
        direction="incoming",
    )
