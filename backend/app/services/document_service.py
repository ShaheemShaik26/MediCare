from __future__ import annotations

import os
import re
import shutil
import time
from dataclasses import dataclass
from datetime import date, datetime
from io import BytesIO
from math import ceil
from pathlib import Path
from uuid import uuid4

from PIL import Image, UnidentifiedImageError
from pypdf import PdfReader
from pypdf.errors import PdfReadError
import pypdfium2 as pdfium
import pytesseract
import pymupdf

from app.config import UPLOAD_DIR, settings
from app.services.medical_ner_service import MedicalNerUnavailable, recognize_medical_entities


class DocumentValidationError(ValueError):
    pass


class DocumentProcessingError(RuntimeError):
    pass


@dataclass
class ExtractedDocument:
    pages: list[str]
    ocr_page_numbers: set[int]


@dataclass(frozen=True)
class ExtractedFactCandidate:
    fact_type: str
    value: str
    confidence: float
    source_excerpt: str
    page_number: int
    event_date: date | None
    numeric_value: float | None
    unit: str | None


MAX_UPLOAD_BYTES = settings.max_upload_size_mb * 1024 * 1024
_SUPPORTED_EXTENSIONS = {".pdf", ".png", ".jpg", ".jpeg", ".txt", ".md"}
_PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
_PDF_SIGNATURE = b"%PDF-"
_MAX_OCR_SECONDS = 60
_TESSERACT_TIMEOUT_SECONDS = 15
_PDF_RENDER_SCALE = 2
_MAX_RENDERED_PIXELS = 40_000_000

_METADATA_DATE_PATTERN = re.compile(
    r"(?i)\b(?:(?:(?:document|report|record|issued|created|printed|visit|service|collection|specimen|test|encounter)\s+date)|"
    r"date\s+of\s+(?:document|report|record|visit|service|collection|specimen|test|encounter)|date(?!\s+of\s+birth))"
    r"\s*[:\-]\s*(\d{4}-\d{2}-\d{2}|[A-Za-z]{3,9}\s+\d{1,2},?\s+\d{4}|\d{1,2}/\d{1,2}/\d{2,4})"
)
_EVENT_DATE_PATTERN = re.compile(
    r"(?i)\b(?:(?:event|visit|test|collection|specimen|service|encounter|procedure|admission|discharge)\s+date|"
    r"date\s+of\s+(?:event|visit|test|collection|service|encounter|procedure|admission|discharge)|"
    r"date\s+(?:collected|performed|recorded|admitted|discharged)|collected|performed|admitted|discharged)"
    r"\s*[:\-]\s*(\d{4}-\d{2}-\d{2}|[A-Za-z]{3,9}\s+\d{1,2},?\s+\d{4}|\d{1,2}/\d{1,2}/\d{2,4})"
)
_FACT_LABELS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("diagnosis", ("diagnosis", "diagnoses", "primary diagnosis", "secondary diagnosis", "final diagnosis", "condition", "medical condition")),
    ("symptom", ("symptom", "symptoms")),
    ("medication", ("medication", "medications", "current medication", "current medications", "medicine", "medicines", "prescription", "prescriptions", "drug", "drugs")),
    ("allergy", ("allergy", "allergies", "drug allergy", "drug allergies", "allergy status")),
    ("lab", ("lab", "test", "tests", "result", "results", "measurement", "measurements", "hba1c", "a1c", "glucose", "hemoglobin", "haemoglobin", "hematocrit", "haematocrit", "blood pressure", "bp", "ldl", "hdl", "cholesterol", "total cholesterol", "triglycerides", "creatinine", "egfr", "bun", "wbc", "rbc", "platelet", "platelets", "sodium", "potassium", "chloride", "bicarbonate", "calcium", "alt", "ast", "tsh", "vitamin d", "bmi", "weight", "height", "temperature", "heart rate", "pulse", "respiratory rate", "oxygen saturation", "spo2")),
    ("procedure", ("procedure", "procedures", "surgery", "surgeries", "hospitalization", "hospitalizations", "visit", "visits")),
    ("provider", ("provider", "providers", "doctor", "doctors", "physician", "physicians", "facility", "facilities", "clinic", "clinics")),
    ("lifestyle_activity", ("exercise", "exercise frequency", "physical activity", "activity", "activity level")),
    ("lifestyle_diet", ("diet", "nutrition")),
    ("lifestyle_tobacco", ("tobacco use", "smoking")),
    ("lifestyle_alcohol", ("alcohol use", "alcohol")),
    ("lifestyle_sleep", ("sleep duration", "sleep hours", "sleep")),
)
_LABEL_TO_TYPE = {
    label: fact_type
    for fact_type, labels in _FACT_LABELS
    for label in labels
}
_ALL_FACT_LABELS = "|".join(
    re.escape(label)
    for label in sorted((label for _, labels in _FACT_LABELS for label in labels), key=len, reverse=True)
)
_FACT_PATTERN = re.compile(
    rf"(?i)(?<![\w])(?P<label>{_ALL_FACT_LABELS})\s*[:=\-–]\s*"
    rf"(?P<value>.*?)(?=\s+(?:{_ALL_FACT_LABELS})\s*[:=\-–]|$)"
)
_SENTENCE_BOUNDARY_PATTERN = re.compile(r"(?<=[.!?])\s+(?=[A-Z])")
_MEASUREMENT_PATTERN = re.compile(
    r"^[<>≤≥]?\s*([+-]?\d+(?:\.\d+)?)\s*"
    r"(mmol/mol|mg/dL|mmol/L|g/dL|mg/L|mL/min(?:/1\.73\s*m2)?|"
    r"(?:[x×]\s*)?10\^(?:9|12)/L|mmHg|bpm|kg|lb|cm|mm|mL|mcg|µg|mg|g|%|°C|°F)$",
    re.IGNORECASE,
)
_LAB_ROW_LABELS = (
    "total cholesterol", "blood pressure", "oxygen saturation", "vitamin d",
    "triglycerides", "creatinine", "hemoglobin", "haemoglobin", "platelets",
    "respiratory rate", "total cholesterol", "blood pressure", "oxygen saturation",
    "hematocrit", "haematocrit", "vitamin d", "triglycerides", "creatinine",
    "hemoglobin", "haemoglobin", "platelets", "temperature", "heart rate",
    "bicarbonate", "glucose", "hba1c", "cholesterol", "potassium", "chloride",
    "sodium", "calcium", "egfr", "tsh", "weight", "height", "spo2", "bmi",
    "wbc", "rbc", "ldl", "hdl", "bun", "alt", "ast", "pulse", "bp", "a1c",
)
_LAB_ROW_PATTERN = re.compile(
    rf"(?i)^\s*(?P<label>{'|'.join(re.escape(label) for label in _LAB_ROW_LABELS)})"
    r"(?:\s*[:=]\s*|\s+)(?P<value>\S(?:.*\S)?)\s*$"
)
_NER_FACT_TYPES = {
    "disease_disorder": "diagnosis",
    "sign_symptom": "symptom",
    "medication": "medication",
    "diagnostic_procedure": "procedure",
    "therapeutic_procedure": "procedure",
    "clinical_event": "medical_event",
    "other_event": "medical_event",
}
_NER_GENERIC_VALUES = {
    "condition", "diagnosis", "disease", "disorder", "drug", "medication",
    "medicine", "procedure", "symptom", "therapy",
}


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

    for line in lines:
        match = _METADATA_DATE_PATTERN.search(line)
        if match:
            metadata["document_date"] = match.group(1)
            break

    provider_match = re.search(r"(?i)(?:provider|doctor|physician|facility|clinic)[:\-]\s*([^\n]+)", text)
    if provider_match:
        metadata["provider_name"] = provider_match.group(1).strip()

    return metadata


def _parse_explicit_event_date(text: str) -> date | None:
    dates = _explicit_event_dates(text)
    return dates[0] if dates else None


def _trim_fact_sentence(value: str) -> str:
    for boundary in _SENTENCE_BOUNDARY_PATTERN.finditer(value):
        preceding_text = value[:boundary.start()].rstrip()
        if re.search(r"\b(?:Dr|Mr|Mrs|Ms|Prof)\.$", preceding_text, re.IGNORECASE):
            continue
        return preceding_text
    return value.strip()


def _is_duplicate_fact(candidate: str, existing: str) -> bool:
    if candidate == existing or f" {candidate} " in f" {existing} " or f" {existing} " in f" {candidate} ":
        return True
    candidate_terms = set(candidate.split())
    existing_terms = set(existing.split())
    overlap = len(candidate_terms & existing_terms)
    return bool(overlap) and overlap / min(len(candidate_terms), len(existing_terms)) >= 0.75


def _entity_matches_context(entity: str, context: str) -> bool:
    phrase_pattern = re.escape(entity).replace(r"\ ", r"\s+")
    return bool(re.search(
        rf"(?<![a-z0-9]){phrase_pattern}s?(?![a-z0-9])",
        context,
    ))


def parse_measurement(value: str) -> tuple[float | None, str | None]:
    measurement_text = value.rsplit(":", 1)[-1].strip() if ":" in value else value.strip()
    match = _MEASUREMENT_PATTERN.fullmatch(measurement_text)
    if not match:
        return None, None
    try:
        numeric_value = float(match.group(1))
    except ValueError:
        return None, None
    return numeric_value, match.group(2)


def _parse_record_date(raw_date: str) -> date | None:
    for date_format in (
        "%Y-%m-%d",
        "%b %d, %Y",
        "%B %d, %Y",
        "%b %d %Y",
        "%B %d %Y",
        "%m/%d/%Y",
        "%m/%d/%y",
    ):
        try:
            return datetime.strptime(raw_date, date_format).date()
        except ValueError:
            continue
    return None


def _explicit_event_dates(text: str) -> list[date]:
    dates: list[date] = []
    for line in text.splitlines():
        match = _EVENT_DATE_PATTERN.search(line)
        if match:
            parsed = _parse_record_date(match.group(1).strip())
            if parsed and parsed not in dates:
                dates.append(parsed)
    return dates


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
            with pymupdf.open(stream=content, filetype="pdf") as pdf_document:
                pages = []
                for page in pdf_document:
                    text = page.get_text("text", sort=True) or ""
                    table_rows = []
                    for table in page.find_tables().tables:
                        for row in table.extract():
                            cells = [str(cell).strip() for cell in row if cell and str(cell).strip()]
                            if len(cells) > 1:
                                table_rows.append("\t".join(cells))
                    if table_rows:
                        text = "\n".join([text.rstrip(), *table_rows]).strip()
                    pages.append(text)
        except (pymupdf.FileDataError, OSError, RuntimeError, ValueError) as exc:
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


def extract_fact_candidates(
    text: str,
    page_number: int = 1,
    is_ocr: bool = False,
) -> list[ExtractedFactCandidate]:
    if not text.strip():
        return []

    candidates: list[ExtractedFactCandidate] = []
    page_event_dates = _explicit_event_dates(text)
    page_event_date = page_event_dates[0] if len(page_event_dates) == 1 else None
    current_event_date = page_event_date
    for line in text.splitlines():
        line_event_date = _parse_explicit_event_date(line)
        if line_event_date:
            current_event_date = line_event_date
        matches = [
            (match.group("label").strip(), _trim_fact_sentence(match.group("value")).rstrip(";,"))
            for match in _FACT_PATTERN.finditer(line)
        ]
        if not matches:
            lab_match = _LAB_ROW_PATTERN.match(line)
            if lab_match:
                matches.append((lab_match.group("label").strip(), lab_match.group("value").strip().rstrip(";,.")))

        event_date = current_event_date
        for label, value in matches:
            if not value:
                continue
            normalized_label = label.lower()
            fact_type = _LABEL_TO_TYPE[normalized_label]
            if fact_type == "lab" and normalized_label not in {
                "lab", "test", "tests", "result", "results", "measurement", "measurements",
            }:
                value = f"{label}: {value}"
            numeric_value, unit = parse_measurement(value) if fact_type == "lab" else (None, None)
            excerpt = line.strip()[:220]
            candidates.append(ExtractedFactCandidate(
                fact_type=fact_type,
                value=value,
                confidence=0.55,
                source_excerpt=f"OCR text: {excerpt}" if is_ocr else excerpt,
                page_number=page_number,
                event_date=event_date,
                numeric_value=numeric_value,
                unit=unit,
            ))

    if settings.medical_ner_enabled:
        try:
            entities = recognize_medical_entities(text)
        except MedicalNerUnavailable as exc:
            raise DocumentProcessingError(str(exc)) from exc

        existing_facts = {
            (candidate.fact_type, re.sub(r"[^a-z0-9]+", " ", candidate.value.lower()).strip())
            for candidate in candidates
        }
        for entity in entities:
            fact_type = _NER_FACT_TYPES.get(entity.label.casefold())
            value = entity.text.strip()
            normalized_value = re.sub(r"[^a-z0-9]+", " ", value.lower()).strip()
            normalized_context = re.sub(r"[^a-z0-9]+", " ", entity.context.lower()).strip()
            is_duplicate = any(
                existing_type == fact_type
                and _is_duplicate_fact(normalized_value, existing_value)
                for existing_type, existing_value in existing_facts
            )
            if (
                fact_type is None
                or entity.score < settings.medical_ner_min_score
                or len(normalized_value) < 3
                or not _entity_matches_context(normalized_value, normalized_context)
                or normalized_value in _NER_GENERIC_VALUES
                or is_duplicate
            ):
                continue
            excerpt = entity.context[:200]
            source_prefix = "OCR + AI suggestion" if is_ocr else "AI suggestion"
            candidate = ExtractedFactCandidate(
                fact_type=fact_type,
                value=value[:2000],
                confidence=entity.score,
                source_excerpt=f"{source_prefix}: {excerpt}",
                page_number=page_number,
                event_date=_parse_explicit_event_date(entity.context) if len(page_event_dates) > 1 else page_event_date,
                numeric_value=None,
                unit=None,
            )
            candidates.append(candidate)
            existing_facts.add((fact_type, normalized_value))

    return candidates


def save_document_to_private_store(file_name: str, content: bytes, user_id: int) -> Path:
    safe_name = sanitize_filename(file_name)
    file_id = uuid4().hex
    destination = UPLOAD_DIR / f"user_{user_id}" / f"{file_id}_{safe_name}"
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(content)
    return destination
