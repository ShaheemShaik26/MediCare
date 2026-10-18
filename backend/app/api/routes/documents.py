from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from app.config import UPLOAD_DIR, settings
from app.database import get_db
from app.deps import get_current_user
from app.models.user import Document, MedicalFact, User
from app.schemas.document import FactSchema, DocumentSchema, ReviewRequest
from app.services.document_service import (
    MAX_UPLOAD_BYTES,
    DocumentProcessingError,
    DocumentValidationError,
    extract_document_metadata,
    extract_facts_from_text,
    extract_document_pages,
    save_document_to_private_store,
    sanitize_filename,
    validate_document_content,
)

router = APIRouter(prefix="/api", tags=["documents"])


@router.get("/documents", response_model=list[DocumentSchema])
def list_documents(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return db.query(Document).filter(Document.owner_id == current_user.id).order_by(Document.uploaded_at.desc()).all()


@router.post("/documents/upload", response_model=DocumentSchema)
async def upload_document(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if not file.filename:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="A file is required")

    chunks: list[bytes] = []
    total_size = 0
    while chunk := await file.read(64 * 1024):
        total_size += len(chunk)
        if total_size > MAX_UPLOAD_BYTES:
            raise HTTPException(
                status_code=status.HTTP_413_CONTENT_TOO_LARGE,
                detail=f"File exceeds the {settings.max_upload_size_mb} MB upload limit.",
            )
        chunks.append(chunk)
    content = b"".join(chunks)
    file_name = sanitize_filename(file.filename)

    try:
        content_type = validate_document_content(file_name, content)
        extracted = await run_in_threadpool(extract_document_pages, content, content_type)
    except DocumentValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(exc),
        ) from exc
    except DocumentProcessingError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc

    pages = extracted.pages
    text = "\n\n".join(pages).strip()
    metadata = extract_document_metadata(text)
    path = save_document_to_private_store(file_name, content, current_user.id)
    document = Document(
        owner_id=current_user.id,
        file_name=file_name,
        content_type=content_type,
        storage_path=str(path),
        preview_text=text[:2000] if text else None,
        status="ocr_review" if extracted.ocr_page_numbers else "processed" if text else "manual_review",
        document_type=metadata.get("document_type"),
        document_date=metadata.get("document_date"),
        provider_name=metadata.get("provider_name"),
    )
    try:
        db.add(document)
        db.flush()
        for page_number, page_text in enumerate(pages, start=1):
            extract_facts_from_text(
                page_text,
                document,
                current_user,
                db,
                page_number,
                is_ocr=page_number in extracted.ocr_page_numbers,
            )
        db.commit()
        db.refresh(document)
    except SQLAlchemyError as exc:
        db.rollback()
        path.unlink(missing_ok=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="The document could not be saved. Please try again.",
        ) from exc

    return document


@router.get("/documents/{document_id}/download")
def download_document(
    document_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    document = (
        db.query(Document)
        .filter(Document.id == document_id, Document.owner_id == current_user.id)
        .first()
    )
    if not document:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")

    path = Path(document.storage_path).resolve()
    user_storage = (UPLOAD_DIR / f"user_{current_user.id}").resolve()
    if not path.is_relative_to(user_storage) or not path.is_file():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document file not found")

    return FileResponse(
        path,
        media_type=document.content_type,
        filename=document.file_name,
        headers={
            "Cache-Control": "private, no-store",
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.get("/documents/{document_id}/facts", response_model=list[FactSchema])
def get_document_facts(document_id: int, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    document = db.query(Document).filter(Document.id == document_id, Document.owner_id == current_user.id).first()
    if not document:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")

    return db.query(MedicalFact).filter(MedicalFact.document_id == document.id, MedicalFact.owner_id == current_user.id).all()


@router.post("/facts/{fact_id}/review", response_model=FactSchema)
def review_fact(
    fact_id: int,
    payload: ReviewRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    fact = db.query(MedicalFact).filter(MedicalFact.id == fact_id, MedicalFact.owner_id == current_user.id).first()
    if not fact:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Fact not found")

    fact.status = payload.status
    db.commit()
    db.refresh(fact)
    return fact


@router.get("/timeline", response_model=list[FactSchema])
def timeline(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return (
        db.query(MedicalFact)
        .filter(MedicalFact.owner_id == current_user.id, MedicalFact.status == "accepted")
        .order_by(MedicalFact.created_at.desc())
        .all()
    )
