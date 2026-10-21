from __future__ import annotations

from collections import deque
from http.client import IncompleteRead
from html import unescape
from html.parser import HTMLParser
import re
from threading import Lock
from time import monotonic
from urllib.error import URLError
from urllib.parse import urlencode, urlsplit
from urllib.request import Request, urlopen
from xml.etree import ElementTree

from app.schemas.knowledge import HealthTopic

_BASE_URL = "https://wsearch.nlm.nih.gov/ws/query"
_MAX_RESPONSE_BYTES = 1_500_000
_CACHE_TTL_SECONDS = 12 * 60 * 60
_MAX_CACHE_ENTRIES = 512
_MAX_REQUESTS_PER_MINUTE = 60
_cache: dict[str, tuple[float, list[HealthTopic]]] = {}
_request_times: deque[float] = deque()
_service_lock = Lock()


class MedicalKnowledgeUnavailable(RuntimeError):
    pass


class _TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []

    def handle_data(self, data: str) -> None:
        cleaned = re.sub(r"\s+", " ", data).strip()
        if cleaned:
            self.parts.append(cleaned)

    def text(self) -> str:
        text = re.sub(r"\s+", " ", " ".join(self.parts)).strip()
        text = re.sub(r"\s+([.,;:!?%)])", r"\1", text)
        return re.sub(r"(\()\s+", r"\1", text)


def _truncate(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    excerpt = text[: limit - 1]
    if " " in excerpt:
        excerpt = excerpt.rsplit(" ", 1)[0]
    return excerpt.rstrip() + "…"


def _plain_text(value: str) -> str:
    parser = _TextExtractor()
    parser.feed(unescape(value))
    parser.close()
    return parser.text()


def _parse_topics(response: bytes) -> list[HealthTopic]:
    if len(response) > _MAX_RESPONSE_BYTES:
        raise MedicalKnowledgeUnavailable("The health information service returned an oversized response.")
    if b"<!DOCTYPE" in response.upper() or b"<!ENTITY" in response.upper():
        raise MedicalKnowledgeUnavailable("The health information service returned an unsupported XML response.")
    try:
        root = ElementTree.fromstring(response)
    except ElementTree.ParseError as exc:
        raise MedicalKnowledgeUnavailable("The health information service returned invalid data.") from exc

    topics: list[HealthTopic] = []
    for document in root.findall("./list/document"):
        url = document.attrib.get("url", "")
        try:
            parsed_url = urlsplit(url)
            port = parsed_url.port
        except ValueError:
            continue
        if (
            parsed_url.scheme != "https"
            or not parsed_url.hostname
            or port not in {None, 443}
            or not (
                parsed_url.hostname.lower() == "medlineplus.gov"
                or parsed_url.hostname.lower().endswith(".medlineplus.gov")
            )
            or parsed_url.username
            or parsed_url.password
        ):
            continue
        content = {
            item.attrib.get("name", "").casefold(): (
                item.text or item.attrib.get("snippet", "")
            )
            for item in document.findall("./content")
        }
        title = _plain_text(content.get("title", "") or document.attrib.get("title", ""))
        summary = _plain_text(
            content.get("snippet", "")
            or document.attrib.get("snippet", "")
            or content.get("fullsummary", "")
        )
        if not title:
            continue
        topics.append(HealthTopic(
            title=_truncate(title, 200),
            summary=_truncate(summary, 600) or "Open the MedlinePlus topic for health information.",
            url=url,
            source="MedlinePlus.gov",
        ))
        if len(topics) == 5:
            break
    return topics


def search_medlineplus(query: str) -> list[HealthTopic]:
    normalized_query = re.sub(r"\s+", " ", query).strip()
    if len(normalized_query) < 2 or len(normalized_query) > 120 or any(ord(char) < 32 for char in normalized_query):
        raise ValueError("Enter a health topic between 2 and 120 characters.")
    cache_key = normalized_query.casefold()
    now = monotonic()
    with _service_lock:
        cached = _cache.get(cache_key)
        if cached and now - cached[0] < _CACHE_TTL_SECONDS:
            return cached[1]

        while _request_times and now - _request_times[0] >= 60:
            _request_times.popleft()
        if len(_request_times) >= _MAX_REQUESTS_PER_MINUTE:
            raise MedicalKnowledgeUnavailable("The health information search limit has been reached. Please try again shortly.")
        _request_times.append(now)

    url = f"{_BASE_URL}?{urlencode({'db': 'healthTopics', 'term': normalized_query, 'rettype': 'brief', 'tool': 'MediCare'})}"
    request = Request(url, headers={"Accept": "application/xml", "User-Agent": "MediCare/0.1 (health topic search)"})
    try:
        with urlopen(request, timeout=8) as response:
            body = response.read(_MAX_RESPONSE_BYTES + 1)
    except (IncompleteRead, URLError, TimeoutError, OSError) as exc:
        raise MedicalKnowledgeUnavailable(
            "MedlinePlus could not be reached. You can try again later or visit MedlinePlus.gov directly."
        ) from exc

    topics = _parse_topics(body)
    with _service_lock:
        if len(_cache) >= _MAX_CACHE_ENTRIES:
            _cache.pop(next(iter(_cache)))
        _cache[cache_key] = (monotonic(), topics)
    return topics
