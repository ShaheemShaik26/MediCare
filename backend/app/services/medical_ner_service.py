from __future__ import annotations

from dataclasses import dataclass
import re
from threading import Lock

from app.config import settings


@dataclass(frozen=True)
class MedicalEntity:
    label: str
    text: str
    score: float
    context: str


class MedicalNerUnavailable(RuntimeError):
    pass


_CHUNK_CHAR_LIMIT = 1000
_pipeline = None
_pipeline_lock = Lock()
_inference_lock = Lock()


def _text_chunks(text: str) -> list[str]:
    chunks: list[str] = []
    for line in text.splitlines():
        for sentence in re.split(r"(?<=[.!?])\s+", line.strip()):
            if not sentence:
                continue
            words = sentence.split()
            current: list[str] = []
            current_length = 0
            for word in words:
                additional_length = len(word) + (1 if current else 0)
                if current and current_length + additional_length > _CHUNK_CHAR_LIMIT:
                    chunks.append(" ".join(current))
                    current = []
                    current_length = 0
                current.append(word)
                current_length += len(word) + (1 if len(current) > 1 else 0)
            if current:
                chunks.append(" ".join(current))
    return chunks


def _get_pipeline():
    global _pipeline
    if _pipeline is not None:
        return _pipeline

    with _pipeline_lock:
        if _pipeline is not None:
            return _pipeline
        try:
            from huggingface_hub.errors import HfHubHTTPError
            from transformers import AutoModelForTokenClassification, AutoTokenizer, pipeline
        except ImportError as exc:
            raise MedicalNerUnavailable(
                "The local medical language-model dependencies are not installed. Install backend requirements and retry."
            ) from exc

        try:
            tokenizer = AutoTokenizer.from_pretrained(settings.medical_ner_model, use_fast=True)
            model = AutoModelForTokenClassification.from_pretrained(
                settings.medical_ner_model,
                use_safetensors=True,
            )
            _pipeline = pipeline(
                "token-classification",
                model=model,
                tokenizer=tokenizer,
                aggregation_strategy="simple",
                device=-1,
            )
        except (HfHubHTTPError, OSError, RuntimeError, ValueError) as exc:
            raise MedicalNerUnavailable(
                "The local medical extraction model could not be loaded or downloaded. Check network access and try again."
            ) from exc
    return _pipeline


def recognize_medical_entities(text: str) -> list[MedicalEntity]:
    chunks = _text_chunks(text)
    if not chunks:
        return []
    local_pipeline = _get_pipeline()

    try:
        with _inference_lock:
            chunk_entities = local_pipeline(chunks, batch_size=8, stride=64)
    except (RuntimeError, ValueError) as exc:
        raise MedicalNerUnavailable("The local medical extraction model could not process this document.") from exc

    entities: list[MedicalEntity] = []
    for chunk, predictions in zip(chunks, chunk_entities):
        for prediction in predictions:
            label = str(prediction.get("entity_group", "")).strip()
            value = re.sub(r"\s+", " ", str(prediction.get("word", ""))).strip()
            start = prediction.get("start")
            end = prediction.get("end")
            if isinstance(start, int) and isinstance(end, int) and 0 <= start < end <= len(chunk):
                context_start = max(0, start - 75)
                context_end = min(len(chunk), end + 75)
                context = chunk[context_start:context_end].strip()
            else:
                context = chunk[:220].strip()
            entities.append(MedicalEntity(
                label=label,
                text=value,
                score=float(prediction.get("score", 0.0)),
                context=context,
            ))
    return entities
