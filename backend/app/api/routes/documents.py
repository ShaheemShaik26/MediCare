from __future__ import annotations

import re
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
from app.schemas.document import (
    FactSchema,
    DocumentSchema,
    DocumentExtractionResponse,
    RecordCitation,
    RecordsAnswer,
    RecordsQuestion,
    ManualFactCreate,
    ReviewRequest,
)
from app.services.document_service import (
    MAX_UPLOAD_BYTES,
    DocumentProcessingError,
    DocumentValidationError,
    extract_document_metadata,
    extract_fact_candidates,
    extract_document_pages,
    parse_measurement,
    save_document_to_private_store,
    sanitize_filename,
    validate_document_content,
)

router = APIRouter(prefix="/api", tags=["documents"])
_QUESTION_STOP_WORDS = {
    "a", "about", "am", "an", "and", "are", "can", "did", "do", "does", "for",
    "from", "have", "has", "in", "is", "it", "me", "my", "of", "on", "or",
    "please", "show", "tell", "the", "to", "was", "were", "what", "when",
    "where", "which", "who", "with", "would", "you",
}
_QUESTION_SYNONYMS = {
    "medications": "medication",
    "medicine": "medication",
    "medicines": "medication",
    "prescription": "medication",
    "prescriptions": "medication",
    "drug": "medication",
    "drugs": "medication",
    "allergies": "allergy",
    "conditions": "diagnosis",
    "condition": "diagnosis",
    "diagnoses": "diagnosis",
    "tests": "lab",
    "results": "lab",
    "measurement": "lab",
    "measurements": "lab",
    "exercise": "lifestyle_activity",
    "activity": "lifestyle_activity",
    "diet": "lifestyle_diet",
    "nutrition": "lifestyle_diet",
    "smoking": "lifestyle_tobacco",
    "tobacco": "lifestyle_tobacco",
    "alcohol": "lifestyle_alcohol",
    "sleep": "lifestyle_sleep",
}


def _question_terms(text: str) -> set[str]:
    terms = {term for term in re.findall(r"[a-z0-9]+", text.lower()) if term not in _QUESTION_STOP_WORDS}
    return {_QUESTION_SYNONYMS.get(term, term) for term in terms}


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
            candidates = await run_in_threadpool(
                extract_fact_candidates,
                page_text,
                page_number,
                page_number in extracted.ocr_page_numbers,
            )
            for candidate in candidates:
                db.add(MedicalFact(
                    owner_id=current_user.id,
                    document_id=document.id,
                    fact_type=candidate.fact_type,
                    value=candidate.value,
                    status="unreviewed",
                    confidence=candidate.confidence,
                    source_excerpt=candidate.source_excerpt,
                    page_number=candidate.page_number,
                    event_date=candidate.event_date,
                    numeric_value=candidate.numeric_value,
                    unit=candidate.unit,
                ))
        db.commit()
        db.refresh(document)
    except DocumentProcessingError as exc:
        db.rollback()
        path.unlink(missing_ok=True)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc
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


@router.post("/documents/{document_id}/extract", response_model=DocumentExtractionResponse)
async def reprocess_document(
    document_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    document = db.query(Document).filter(
        Document.id == document_id,
        Document.owner_id == current_user.id,
    ).first()
    if not document:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")

    path = Path(document.storage_path).resolve()
    user_storage = (UPLOAD_DIR / f"user_{current_user.id}").resolve()
    if not path.is_relative_to(user_storage) or not path.is_file():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document file not found")

    try:
        content = await run_in_threadpool(path.read_bytes)
        content_type = validate_document_content(document.file_name, content)
        extracted = await run_in_threadpool(extract_document_pages, content, content_type)
        candidates = []
        for page_number, page_text in enumerate(extracted.pages, start=1):
            candidates.extend(await run_in_threadpool(
                extract_fact_candidates,
                page_text,
                page_number,
                page_number in extracted.ocr_page_numbers,
            ))
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
    except OSError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="The document file could not be read for extraction.",
        ) from exc

    existing_facts = db.query(MedicalFact).filter(
        MedicalFact.document_id == document.id,
        MedicalFact.owner_id == current_user.id,
    ).all()
    existing_keys = {
        (
            fact.fact_type,
            re.sub(r"[^a-z0-9]+", " ", fact.value.casefold()).strip(),
            fact.page_number,
        )
        for fact in existing_facts
    }
    new_facts: list[MedicalFact] = []
    updated_fact_count = 0
    for candidate in candidates:
        key = (
            candidate.fact_type,
            re.sub(r"[^a-z0-9]+", " ", candidate.value.casefold()).strip(),
            candidate.page_number,
        )
        if key in existing_keys:
            matching_fact = next(
                (
                    fact for fact in existing_facts
                    if (
                        fact.fact_type,
                        re.sub(r"[^a-z0-9]+", " ", fact.value.casefold()).strip(),
                        fact.page_number,
                    ) == key
                ),
                None,
            )
            if (
                matching_fact
                and matching_fact.status == "unreviewed"
                and matching_fact.event_date is None
                and candidate.event_date is not None
            ):
                matching_fact.event_date = candidate.event_date
                updated_fact_count += 1
            continue
        fact = MedicalFact(
            owner_id=current_user.id,
            document_id=document.id,
            fact_type=candidate.fact_type,
            value=candidate.value,
            status="unreviewed",
            confidence=candidate.confidence,
            source_excerpt=candidate.source_excerpt,
            page_number=candidate.page_number,
            event_date=candidate.event_date,
            numeric_value=candidate.numeric_value,
            unit=candidate.unit,
        )
        db.add(fact)
        new_facts.append(fact)
        existing_keys.add(key)

    document.status = (
        "ocr_review"
        if extracted.ocr_page_numbers
        else "processed"
        if any(page.strip() for page in extracted.pages)
        else "manual_review"
    )
    try:
        db.commit()
    except SQLAlchemyError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Extracted details could not be saved. Please try again.",
        ) from exc

    return DocumentExtractionResponse(
        document_id=document.id,
        extracted_fact_count=len(new_facts),
        updated_fact_count=updated_fact_count,
        status=document.status,
    )


@router.post(
    "/documents/{document_id}/facts",
    response_model=FactSchema,
    status_code=status.HTTP_201_CREATED,
)
def create_manual_fact(
    document_id: int,
    payload: ManualFactCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    document = db.query(Document).filter(
        Document.id == document_id,
        Document.owner_id == current_user.id,
    ).first()
    if not document:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")

    numeric_value, unit = parse_measurement(payload.value) if payload.fact_type == "lab" else (None, None)
    fact = MedicalFact(
        owner_id=current_user.id,
        document_id=document.id,
        fact_type=payload.fact_type,
        value=payload.value.strip(),
        status="unreviewed",
        confidence=0.5,
        source_excerpt=f"User-entered from {document.file_name}; verify against the original before accepting.",
        page_number=payload.page_number,
        event_date=payload.event_date,
        numeric_value=numeric_value,
        unit=unit,
    )
    db.add(fact)
    db.commit()
    db.refresh(fact)
    return fact


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

    if "fact_type" in payload.model_fields_set and payload.fact_type is not None:
        fact.fact_type = payload.fact_type.strip()
    if "value" in payload.model_fields_set and payload.value is not None:
        fact.value = payload.value.strip()
        fact.numeric_value, fact.unit = parse_measurement(fact.value)
    if payload.clear_event_date:
        fact.event_date = None
    elif "event_date" in payload.model_fields_set:
        fact.event_date = payload.event_date
    fact.status = payload.status
    db.commit()
    db.refresh(fact)
    return fact


@router.post("/records/ask", response_model=RecordsAnswer)
def ask_about_records(
    payload: RecordsQuestion,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    terms = _question_terms(payload.question)
    if not terms:
        return RecordsAnswer(
            answer="Please include a specific condition, medication, test, or detail to look for in your reviewed records.",
            insufficient_evidence=True,
            possible_conflict=False,
            citations=[],
        )

    accepted_facts = (
        db.query(MedicalFact, Document)
        .join(Document, Document.id == MedicalFact.document_id)
        .filter(
            MedicalFact.owner_id == current_user.id,
            Document.owner_id == current_user.id,
            MedicalFact.status == "accepted",
        )
        .all()
    )
    matches: list[tuple[int, MedicalFact, Document]] = []
    for fact, document in accepted_facts:
        searchable_text = f"{fact.fact_type} {fact.value}".lower()
        fact_terms = _question_terms(searchable_text)
        overlap = terms & fact_terms
        if overlap:
            matches.append((len(overlap), fact, document))
    matches.sort(
        key=lambda item: (
            item[0],
            item[1].event_date.isoformat() if item[1].event_date else "",
            item[1].created_at.isoformat(),
        ),
        reverse=True,
    )
    matches = matches[:10]
    if not matches:
        return RecordsAnswer(
            answer=(
                "I couldn't find relevant information in your reviewed records. "
                "That does not mean the condition, medication, or result is absent; "
                "it may not be present in the documents you uploaded or reviewed."
            ),
            insufficient_evidence=True,
            possible_conflict=False,
            citations=[],
        )

    relevant = [match for score, *match in matches if score == matches[0][0]]
    values_by_type: dict[str, set[str]] = {}
    for fact, _document in relevant:
        values_by_type.setdefault(fact.fact_type, set()).add(fact.value.casefold().strip())
    possible_conflict = any(len(values) > 1 for values in values_by_type.values())
    if possible_conflict:
        answer = (
            "Your reviewed records contain differing entries for the same type of information. "
            "I can't determine which is current; please compare the cited originals with a healthcare professional."
        )
    else:
        details = "; ".join(f"{fact.fact_type.replace('_', ' ')}: {fact.value}" for fact, _document in relevant[:5])
        answer = f"Your reviewed records include: {details}."

    citations = [
        RecordCitation(
            document_id=fact.document_id,
            file_name=document.file_name,
            page_number=fact.page_number,
            event_date=fact.event_date,
            excerpt=fact.source_excerpt,
        )
        for fact, document in relevant
    ]
    return RecordsAnswer(
        answer=answer,
        insufficient_evidence=False,
        possible_conflict=possible_conflict,
        citations=citations,
    )


@router.get("/timeline", response_model=list[FactSchema])
def timeline(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return (
        db.query(MedicalFact)
        .filter(
            MedicalFact.owner_id == current_user.id,
            MedicalFact.status.in_(("accepted", "unreviewed")),
        )
        .order_by(MedicalFact.event_date.desc().nullslast(), MedicalFact.created_at.desc())
        .all()
    )
