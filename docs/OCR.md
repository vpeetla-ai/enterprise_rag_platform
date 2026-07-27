# OCR path (Phase 5 — optional)

Scanned PDFs with no extractable text return:

```json
{"detail":[{"code":"ocr_required","message":"..."}]}
```

## Enable OCR

```bash
RAG_OCR_ENABLED=true
# Requires system Tesseract + PyMuPDF OCR path (get_textpage_ocr)
```

When enabled, `extract_pdf_pages` retries via PyMuPDF OCR. Failures return `ocr_failed` (not a silent empty index). Cost: CPU/time on the API host — labeled in [COST.md](COST.md) / [PROFILES.md](PROFILES.md).

Until OCR deps are present, upload a text-layer PDF or convert offline.
