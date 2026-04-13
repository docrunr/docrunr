"""Parser package — import modules to trigger registration and export parser classes."""

from .email import EmlParser, MsgParser
from .html_parser import BeautifulSoupHtmlParser, MarkItDownHtmlParser
from .image import DoclingImageParser
from .office import (
    DoclingOfficeParser,
    KreuzbergOfficeParser,
    MarkItDownOfficeParser,
)
from .pdf import DoclingPdfParser, MarkItDownPdfParser, PypdfiumParser
from .text import CsvParser, JsonParser, PlainTextParser, XmlParser

__all__ = [
    "BeautifulSoupHtmlParser",
    "CsvParser",
    "DoclingImageParser",
    "DoclingOfficeParser",
    "DoclingPdfParser",
    "EmlParser",
    "JsonParser",
    "KreuzbergOfficeParser",
    "MarkItDownHtmlParser",
    "MarkItDownOfficeParser",
    "MarkItDownPdfParser",
    "MsgParser",
    "PlainTextParser",
    "PypdfiumParser",
    "XmlParser",
]
