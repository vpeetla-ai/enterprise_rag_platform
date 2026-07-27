"""Server-side PDF page extraction (ADR-0007) + optional OCR (Phase 5)."""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class PdfExtractResult:
    pages: tuple[tuple[int, str], ...]
    page_count: int
    char_count: int
    warnings: tuple[str, ...]


class PdfExtractError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def ocr_enabled() -> bool:
    return os.getenv("RAG_OCR_ENABLED", "").strip().lower() in {"1", "true", "yes", "on"}


def extract_pdf_pages(
    data: bytes,
    *,
    max_pages: int = 100,
    max_chars: int = 500_000,
) -> PdfExtractResult:
    """Extract text per page using PyMuPDF. Raises PdfExtractError on failure."""
    try:
        import fitz  # pymupdf
    except ImportError as exc:
        raise PdfExtractError(
            "pdf_deps_missing",
            "pymupdf is required for PDF ingest. Install with: pip install '.[pdf]'",
        ) from exc

    try:
        doc = fitz.open(stream=data, filetype="pdf")
    except Exception as exc:  # noqa: BLE001
        raise PdfExtractError("invalid_pdf", f"Could not open PDF: {exc}") from exc

    warnings: list[str] = []
    pages: list[tuple[int, str]] = []
    total_chars = 0
    limit = min(doc.page_count, max_pages)
    if doc.page_count > max_pages:
        warnings.append(f"truncated_pages:{doc.page_count}->{max_pages}")

    for i in range(limit):
        page = doc.load_page(i)
        text = (page.get_text("text") or "").strip()
        if total_chars + len(text) > max_chars:
            remain = max(0, max_chars - total_chars)
            text = text[:remain]
            warnings.append("truncated_chars")
            if text:
                pages.append((i + 1, text))
            break
        total_chars += len(text)
        pages.append((i + 1, text))

    if not any(t.strip() for _, t in pages):
        if ocr_enabled():
            ocr_pages, ocr_chars, ocr_warnings = _ocr_extract(doc, max_pages=limit, max_chars=max_chars)
            doc.close()
            if not any(t.strip() for _, t in ocr_pages):
                raise PdfExtractError(
                    "ocr_failed",
                    "OCR enabled but produced no text. Install Tesseract + pymupdf OCR support, "
                    "or upload a text-layer PDF.",
                )
            return PdfExtractResult(
                pages=tuple(ocr_pages),
                page_count=len(ocr_pages),
                char_count=ocr_chars,
                warnings=tuple([*warnings, "ocr_used", *ocr_warnings]),
            )
        doc.close()
        raise PdfExtractError(
            "ocr_required",
            "No extractable text (likely scanned PDF). Set RAG_OCR_ENABLED=true with OCR deps, "
            "or upload a text-layer PDF.",
        )

    doc.close()
    return PdfExtractResult(
        pages=tuple(pages),
        page_count=len(pages),
        char_count=total_chars,
        warnings=tuple(warnings),
    )


def _ocr_extract(
    doc: object,
    *,
    max_pages: int,
    max_chars: int,
) -> tuple[list[tuple[int, str]], int, list[str]]:
    """Best-effort OCR via PyMuPDF TextPage OCR (needs Tesseract on host)."""
    warnings: list[str] = []
    pages: list[tuple[int, str]] = []
    total_chars = 0
    for i in range(max_pages):
        page = doc.load_page(i)  # type: ignore[attr-defined]
        text = ""
        try:
            # PyMuPDF >= 1.23 — requires system tesseract
            tp = page.get_textpage_ocr(dpi=150, full=True)  # type: ignore[attr-defined]
            text = (page.get_text("text", textpage=tp) or "").strip()
        except Exception as exc:  # noqa: BLE001
            warnings.append(f"ocr_page_error:{i + 1}:{type(exc).__name__}")
            continue
        if total_chars + len(text) > max_chars:
            remain = max(0, max_chars - total_chars)
            text = text[:remain]
            warnings.append("truncated_chars")
            if text:
                pages.append((i + 1, text))
            break
        total_chars += len(text)
        pages.append((i + 1, text))
    return pages, total_chars, warnings
