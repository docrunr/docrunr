from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
OUT_ROOT = PROJECT_ROOT / ".data" / "downloads"
DEFAULT_TIMEOUT = 20
USER_AGENT = "DocRunr-SampleFetcher/0.2"

DEFAULT_SOURCES = [
    "catalog.data.gov",
    "open.canada.ca",
    "ckan.opendata.swiss",
    "data.overheid.nl",
    "data.europa.eu",
]


@dataclass(frozen=True)
class Source:
    key: str
    kind: str  # ckan | europa
    endpoint: str
    fq_mode: str = "plain"  # plain | uri


@dataclass
class Target:
    aliases: set[str]
    extensions: set[str]
    mime_types: set[str]
    ckan_format_ids: set[str]
    europa_format_ids: set[str]


@dataclass
class Candidate:
    url: str
    source: str
    format_hint: str | None
    mime_hint: str | None


@dataclass
class PlannedDownload:
    candidate: Candidate
    final_url: str
    content_type: str | None
    content_length: int | None


SOURCES: dict[str, Source] = {
    "catalog.data.gov": Source(
        "catalog.data.gov",
        "ckan",
        "https://catalog.data.gov/api/3/action/package_search",
        "plain",
    ),
    "open.canada.ca": Source(
        "open.canada.ca",
        "ckan",
        "https://open.canada.ca/data/en/api/3/action/package_search",
        "plain",
    ),
    "ckan.opendata.swiss": Source(
        "ckan.opendata.swiss",
        "ckan",
        "https://ckan.opendata.swiss/api/3/action/package_search",
        "plain",
    ),
    "data.overheid.nl": Source(
        "data.overheid.nl",
        "ckan",
        "https://data.overheid.nl/data/api/3/action/package_search",
        "uri",
    ),
    "data.europa.eu": Source(
        "data.europa.eu", "europa", "https://data.europa.eu/api/hub/search/search"
    ),
}

MIME_DEFS: dict[str, dict[str, set[str]]] = {
    "pdf": {
        "ext": {"pdf"},
        "mime": {"application/pdf"},
        "ckan": {"PDF"},
        "eu": {"PDF"},
    },
    "pptx": {
        "ext": {"pptx"},
        "mime": {"application/vnd.openxmlformats-officedocument.presentationml.presentation"},
        "ckan": {"PPTX"},
        "eu": {"PPTX"},
    },
    "docx": {
        "ext": {"docx"},
        "mime": {"application/vnd.openxmlformats-officedocument.wordprocessingml.document"},
        "ckan": {"DOCX"},
        "eu": {"DOCX"},
    },
    "xlsx": {
        "ext": {"xlsx"},
        "mime": {"application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"},
        "ckan": {"XLSX"},
        "eu": {"XLSX"},
    },
    "csv": {
        "ext": {"csv"},
        "mime": {"text/csv", "application/csv"},
        "ckan": {"CSV"},
        "eu": {"CSV"},
    },
    "json": {
        "ext": {"json"},
        "mime": {"application/json", "text/json"},
        "ckan": {"JSON"},
        "eu": {"JSON"},
    },
    "xml": {
        "ext": {"xml"},
        "mime": {"application/xml", "text/xml"},
        "ckan": {"XML", "RDF XML"},
        "eu": {"XML"},
    },
    "html": {
        "ext": {"html", "htm"},
        "mime": {"text/html", "application/xhtml+xml"},
        "ckan": {"HTML"},
        "eu": {"HTML"},
    },
    "txt": {
        "ext": {"txt"},
        "mime": {"text/plain"},
        "ckan": {"TXT", "TEXT"},
        "eu": {"TXT"},
    },
}

MIME_TO_EXT = {
    "application/pdf": "pdf",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation": "pptx",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": "docx",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": "xlsx",
    "text/csv": "csv",
    "application/csv": "csv",
    "application/json": "json",
    "text/json": "json",
    "application/xml": "xml",
    "text/xml": "xml",
    "text/html": "html",
    "application/xhtml+xml": "html",
    "text/plain": "txt",
}
