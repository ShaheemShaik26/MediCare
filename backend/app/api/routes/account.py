from __future__ import annotations

import json
import os
import shutil
import tempfile
import uuid
import zipfile
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Response, status
from fastapi.responses import FileResponse
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.config import UPLOAD_DIR, settings
from app.database import get_db
from app.deps import CSRF_COOKIE_NAME, SESSION_COOKIE_NAME, get_current_user
from app.models.user import Document, LifestyleProfile, MedicalFact, User
from app.schemas.account import AccountDeleteRequest
from app.services.auth_service import verify_password
from app.services.document_service import sanitize_filename

router = APIRouter(prefix="/api/account", tags=["account"])


def _user_storage_path(user_id: int) -> Path:
    storage_root = UPLOAD_DIR.resolve()
    user_path = (storage_root / f"user_{user_id}").resolve()
    if user_path.parent != storage_root:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Invalid private storage path")
    return user_path


@router.get("/export")
def export_account(
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    documents = (
        db.query(Document)
        .filter(Document.owner_id == current_user.id)
        .order_by(Document.id)
        .all()
    )
    facts = (
        db.query(MedicalFact)
        .filter(MedicalFact.owner_id == current_user.id)
        .order_by(MedicalFact.id)
        .all()
    )
    lifestyle_profile = (
        db.query(LifestyleProfile)
        .filter(LifestyleProfile.owner_id == current_user.id)
        .first()
    )

    export_dir = Path(tempfile.mkdtemp(prefix="medicare_export_", dir=UPLOAD_DIR))
    archive_path = export_dir / "medicare-export.zip"
    user_storage = _user_storage_path(current_user.id)

    export_data = {
        "account": {
            "id": current_user.id,
            "email": current_user.email,
            "full_name": current_user.full_name,
            "created_at": current_user.created_at.isoformat(),
        },
        "documents": [
            {
                "id": item.id,
                "file_name": item.file_name,
                "content_type": item.content_type,
                "status": item.status,
                "document_type": item.document_type,
                "document_date": item.document_date,
                "provider_name": item.provider_name,
                "preview_text": item.preview_text,
                "uploaded_at": item.uploaded_at.isoformat(),
            }
            for item in documents
        ],
        "facts": [
            {
                "id": fact.id,
                "document_id": fact.document_id,
                "fact_type": fact.fact_type,
                "value": fact.value,
                "status": fact.status,
                "confidence": fact.confidence,
                "source_excerpt": fact.source_excerpt,
                "page_number": fact.page_number,
                "event_date": fact.event_date.isoformat() if fact.event_date else None,
                "numeric_value": fact.numeric_value,
                "unit": fact.unit,
                "created_at": fact.created_at.isoformat(),
            }
            for fact in facts
        ],
        "lifestyle_profile": (
            {
                "activity_frequency": lifestyle_profile.activity_frequency,
                "diet_notes": lifestyle_profile.diet_notes,
                "sleep_hours": lifestyle_profile.sleep_hours,
                "tobacco_use": lifestyle_profile.tobacco_use,
                "alcohol_frequency": lifestyle_profile.alcohol_frequency,
                "notes": lifestyle_profile.notes,
                "updated_at": lifestyle_profile.updated_at.isoformat(),
            }
            if lifestyle_profile
            else None
        ),
        "exported_at": datetime.now(timezone.utc).isoformat(),
    }

    export_completed = False
    try:
        with zipfile.ZipFile(archive_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("records.json", json.dumps(export_data, indent=2))
            for item in documents:
                source_path = Path(item.storage_path).resolve()
                if not source_path.is_relative_to(user_storage) or not source_path.is_file():
                    raise HTTPException(
                        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                        detail=f"Could not include original document {item.id} in the export.",
                    )
                archive.write(
                    source_path,
                    arcname=f"documents/{item.id}_{sanitize_filename(item.file_name)}",
                )
        export_completed = True
    finally:
        if not export_completed:
            shutil.rmtree(export_dir, ignore_errors=True)

    background_tasks.add_task(shutil.rmtree, export_dir, ignore_errors=True)
    return FileResponse(
        archive_path,
        media_type="application/zip",
        filename="medicare-export.zip",
        headers={"Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff"},
        background=background_tasks,
    )


@router.delete("", status_code=status.HTTP_204_NO_CONTENT)
def delete_account(
    payload: AccountDeleteRequest,
    response: Response,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> None:
    if not verify_password(payload.password, current_user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Password confirmation failed")

    user_storage = _user_storage_path(current_user.id)
    quarantine_path = UPLOAD_DIR / f".deleting_user_{current_user.id}_{uuid.uuid4().hex}"
    moved_storage = user_storage.exists()
    if moved_storage:
        os.replace(user_storage, quarantine_path)

    try:
        db.query(LifestyleProfile).filter(LifestyleProfile.owner_id == current_user.id).delete(
            synchronize_session=False
        )
        db.query(MedicalFact).filter(MedicalFact.owner_id == current_user.id).delete(synchronize_session=False)
        db.query(Document).filter(Document.owner_id == current_user.id).delete(synchronize_session=False)
        db.delete(current_user)
        db.commit()
    except SQLAlchemyError as exc:
        db.rollback()
        if moved_storage:
            os.replace(quarantine_path, user_storage)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="The account could not be deleted. Please try again.",
        ) from exc

    if moved_storage:
        try:
            shutil.rmtree(quarantine_path)
        except OSError as exc:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Account records were deleted, but private file cleanup failed. Contact support.",
            ) from exc

    for cookie_name, httponly in ((SESSION_COOKIE_NAME, True), (CSRF_COOKIE_NAME, False)):
        response.delete_cookie(
            key=cookie_name,
            path="/",
            secure=settings.secure_cookies,
            httponly=httponly,
            samesite="lax",
        )
