"""Server-side PDF page extraction (ADR-0007)."""

from __future__ import annotations

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
        text = page.get_text("text") or ""
        text = text.strip()
        if total_chars + len(text) > max_chars:
            remain = max(0, max_chars - total_chars)
            text = text[:remain]
            warnings.append("truncated_chars")
            if text:
                pages.append((i + 1, text))
            break
        total_chars += len(text)
        pages.append((i + 1, text))

    doc.close()
    if not any(t.strip() for _, t in pages):
        raise PdfExtractError(
            "ocr_required",
            "No extractable text (likely scanned PDF). Enable OCR path or upload a text PDF.",
        )
    return PdfExtractResult(
        pages=tuple(pages),
        page_count=len(pages),
        char_count=total_chars,
        warnings=tuple(warnings),
    )
