"""Parsing agent — turns raw PDF/PPTX files into structured text."""

from agents.parsing.extractor import ParsedDocument, extract_text

__all__ = ["ParsedDocument", "extract_text"]
