from __future__ import annotations

import os
import re
import shutil
import time
from dataclasses import dataclass
from io import BytesIO
from math import ceil
from pathlib import Path
from typing import Iterable
from uuid import uuid4

from PIL import Image, UnidentifiedImageError
from pypdf import PdfReader
from pypdf.errors import PdfReadError
import pypdfium2 as pdfium
import pytesseract
from sqlalchemy.orm import Session

from app.config import UPLOAD_DIR, settings
from app.models.user import Document, MedicalFact, User


class DocumentValidationError(ValueError):
    pass


class DocumentProcessingError(RuntimeError):
    pass


@dataclass
class ExtractedDocument:
    pages: list[str]
    ocr_page_numbers: set[int]


MAX_UPLOAD_BYTES = settings.max_upload_size_mb * 1024 * 1024
_SUPPORTED_EXTENSIONS = {".pdf", ".png", ".jpg", ".jpeg", ".txt", ".md"}
_PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
_PDF_SIGNATURE = b"%PDF-"
_MAX_OCR_SECONDS = 60
_TESSERACT_TIMEOUT_SECONDS = 15
_PDF_RENDER_SCALE = 2
_MAX_RENDERED_PIXELS = 40_000_000

_DATE_PATTERNS = [
    r"\b(?:\d{4}-\d{2}-\d{2})\b",
    r"\b(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)[a-z]*\s+\d{1,2},\s+\d{4}\b",
    r"\b\d{1,2}/\d{1,2}/\d{2,4}\b",
]


def sanitize_filename(file_name: str) -> str:
    safe_name = Path(file_name.replace("\\", "/")).name
    return re.sub(r"[^A-Za-z0-9._-]", "_", safe_name)[:180] or "upload"


def validate_document_content(file_name: str, content: bytes) -> str:
    extension = Path(file_name).suffix.lower()
    if extension not in _SUPPORTED_EXTENSIONS:
        raise DocumentValidationError("Supported uploads are PDF, PNG, JPEG, TXT, and MD files.")
    if not content:
        raise DocumentValidationError("The uploaded file is empty.")
    if len(content) > MAX_UPLOAD_BYTES:
        raise DocumentValidationError(f"File exceeds the {settings.max_upload_size_mb} MB upload limit.")

    if content.startswith(_PDF_SIGNATURE):
        detected_type = "application/pdf"
    elif content.startswith(_PNG_SIGNATURE):
        detected_type = "image/png"
    elif content.startswith(b"\xff\xd8\xff"):
        detected_type = "image/jpeg"
    else:
        if extension not in {".txt", ".md"} or b"\x00" in content:
            raise DocumentValidationError("File content does not match a supported document type.")
        try:
            content.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise DocumentValidationError("Text uploads must be valid UTF-8.") from exc
        detected_type = "text/plain"

    expected_extensions = {
        "application/pdf": {".pdf"},
        "image/png": {".png"},
        "image/jpeg": {".jpg", ".jpeg"},
        "text/plain": {".txt", ".md"},
    }
    if extension not in expected_extensions[detected_type]:
        raise DocumentValidationError("File extension does not match the detected file type.")

    if detected_type.startswith("image/"):
        try:
            with Image.open(BytesIO(content)) as image:
                image.verify()
        except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as exc:
            raise DocumentValidationError("Image file is damaged or invalid.") from exc

    return detected_type


def extract_document_metadata(text: str) -> dict[str, str | None]:
    metadata: dict[str, str | None] = {"document_type": None, "document_date": None, "provider_name": None}

    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if not lines:
        return metadata

    first_line = lines[0]
    for label in ["Visit Summary", "Lab Results", "Medication List", "Progress Note", "Discharge Summary", "Referral Note"]:
        if label.lower() in first_line.lower():
            metadata["document_type"] = label
            break
    if metadata["document_type"] is None:
        metadata["document_type"] = "Medical record"

    for pattern in _DATE_PATTERNS:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            metadata["document_date"] = match.group(0)
            break

    provider_match = re.search(r"(?i)(?:provider|doctor|physician|facility|clinic)[:\-]\s*([^\n]+)", text)
    if provider_match:
        metadata["provider_name"] = provider_match.group(1).strip()

    return metadata


def _get_ocr_engine() -> tuple[str, str] | None:
    if not settings.ocr_enabled:
        return None

    configured_command = settings.tesseract_cmd
    command_path = Path(configured_command).expanduser()
    command = str(command_path) if command_path.is_file() else shutil.which(configured_command)
    if command is None:
        program_files = Path(os.environ.get("ProgramFiles", r"C:\Program Files"))
        installed_command = program_files / "Tesseract-OCR" / "tesseract.exe"
        if installed_command.is_file():
            command = str(installed_command)
    if command is None:
        return None

    pytesseract.pytesseract.tesseract_cmd = command
    try:
        available_languages = set(pytesseract.get_languages())
    except pytesseract.TesseractError as exc:
        raise DocumentProcessingError("The local OCR engine could not load its language data.") from exc
    required_languages = set(settings.ocr_languages.split("+"))
    if not required_languages.issubset(available_languages):
        missing = ", ".join(sorted(required_languages - available_languages))
        raise DocumentProcessingError(f"The local OCR engine is missing configured language data: {missing}.")
    return command, ""


def _recognize_image(
    image: Image.Image,
    engine: tuple[str, str],
    deadline: float,
) -> str:
    remaining_seconds = deadline - time.monotonic()
    if remaining_seconds <= 0:
        raise DocumentProcessingError("OCR exceeded the per-document processing time limit.")
    try:
        return pytesseract.image_to_string(
            image,
            lang=settings.ocr_languages,
            config=engine[1],
            timeout=min(_TESSERACT_TIMEOUT_SECONDS, remaining_seconds),
        )
    except (pytesseract.TesseractError, pytesseract.TesseractNotFoundError, RuntimeError) as exc:
        raise DocumentProcessingError(
            "Local OCR failed or timed out. The document was not saved; please retry or review it manually."
        ) from exc


def _ocr_pdf_pages(content: bytes, pages: list[str], blank_page_numbers: list[int]) -> set[int]:
    engine = _get_ocr_engine()
    if engine is None or not blank_page_numbers:
        return set()

    deadline = time.monotonic() + _MAX_OCR_SECONDS
    ocr_page_numbers: set[int] = set()
    try:
        with pdfium.PdfDocument(content) as pdf_document:
            for page_number in blank_page_numbers:
                page = pdf_document[page_number - 1]
                bitmap = None
                try:
                    width, height = page.get_size()
                    rendered_width = ceil(width * _PDF_RENDER_SCALE)
                    rendered_height = ceil(height * _PDF_RENDER_SCALE)
                    if rendered_width * rendered_height > _MAX_RENDERED_PIXELS:
                        raise DocumentValidationError(
                            "A scanned PDF page exceeds the 40-megapixel OCR processing limit."
                        )
                    bitmap = page.render(scale=_PDF_RENDER_SCALE)
                    with bitmap.to_pil() as image:
                        pages[page_number - 1] = _recognize_image(image, engine, deadline).strip()
                    if pages[page_number - 1]:
                        ocr_page_numbers.add(page_number)
                finally:
                    if bitmap is not None:
                        bitmap.close()
                    page.close()
    except DocumentValidationError:
        raise
    except (pdfium.PdfiumError, OSError, ValueError) as exc:
        raise DocumentProcessingError("The scanned PDF could not be rendered for local OCR.") from exc
    return ocr_page_numbers


def extract_document_pages(content: bytes, content_type: str) -> ExtractedDocument:
    if content_type == "application/pdf":
        try:
            reader = PdfReader(BytesIO(content), strict=True)
            if reader.is_encrypted:
                raise DocumentValidationError("Encrypted PDFs are not supported. Please upload an unlocked copy.")
            if not reader.pages:
                raise DocumentValidationError("The PDF contains no pages.")
            if len(reader.pages) > 100:
                raise DocumentValidationError("PDFs are limited to 100 pages.")
        except (PdfReadError, OSError, ValueError) as exc:
            if isinstance(exc, DocumentValidationError):
                raise
            raise DocumentValidationError("The PDF is damaged or cannot be read.") from exc
        try:
            pages = [page.extract_text() or "" for page in reader.pages]
        except (PdfReadError, OSError, ValueError) as exc:
            raise DocumentValidationError("Text could not be extracted from this PDF.") from exc
        blank_page_numbers = [number for number, text in enumerate(pages, start=1) if not text.strip()]
        return ExtractedDocument(
            pages=pages,
            ocr_page_numbers=_ocr_pdf_pages(content, pages, blank_page_numbers),
        )

    if content_type == "text/plain":
        return ExtractedDocument([content.decode("utf-8", errors="replace")], set())

    if content_type in {"image/png", "image/jpeg"}:
        with Image.open(BytesIO(content)) as image:
            if image.width * image.height > 40_000_000:
                raise DocumentValidationError("Image dimensions exceed the 40-megapixel processing limit.")
            engine = _get_ocr_engine()
            if engine is None:
                return ExtractedDocument([""], set())
            deadline = time.monotonic() + _MAX_OCR_SECONDS
            text = _recognize_image(image, engine, deadline).strip()
        return ExtractedDocument([text], {1} if text else set())

    raise DocumentValidationError("Unsupported document type.")


def extract_facts_from_text(
    text: str,
    document: Document,
    user: User,
    db: Session,
    page_number: int = 1,
    is_ocr: bool = False,
) -> Iterable[MedicalFact]:
    if not text.strip():
        return []

    patterns = {
        "diagnosis": r"(?i)(diagnosis|diagnoses|condition)[:\-]\s*([^\n]+)",
        "medication": r"(?i)(medication|medicine|prescription)[:\-]\s*([^\n]+)",
        "allergy": r"(?i)(allergy|allergies)[:\-]\s*([^\n]+)",
        "lab": r"(?i)(lab|test|result)[:\-]\s*([^\n]+)",
        "procedure": r"(?i)(procedure|hospitalization|visit)[:\-]\s*([^\n]+)",
        "provider": r"(?i)(provider|doctor|physician|facility|clinic)[:\-]\s*([^\n]+)",
    }

    created_facts: list[MedicalFact] = []
    for fact_type, pattern in patterns.items():
        matches = re.finditer(pattern, text)
        for match in matches:
            value = match.group(2).strip()
            if not value:
                continue
            if fact_type == "medication":
                value = re.sub(r"\s+on\s+\d{4}-\d{2}-\d{2}", "", value, flags=re.IGNORECASE)
            excerpt = match.group(0).strip()[:220]
            fact = MedicalFact(
                owner_id=user.id,
                document_id=document.id,
                fact_type=fact_type,
                value=value,
                status="unreviewed",
                confidence=0.55,
                source_excerpt=f"OCR text: {excerpt}" if is_ocr else excerpt,
                page_number=page_number,
            )
            db.add(fact)
            created_facts.append(fact)

    db.flush()
    return created_facts


def save_document_to_private_store(file_name: str, content: bytes, user_id: int) -> Path:
    safe_name = sanitize_filename(file_name)
    file_id = uuid4().hex
    destination = UPLOAD_DIR / f"user_{user_id}" / f"{file_id}_{safe_name}"
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(content)
    return destination
