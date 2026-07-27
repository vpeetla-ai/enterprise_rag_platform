# OCR path — optional (not the product bar)

**Product bar:** text-layer PDFs with page-specific citations.

Scanned PDFs with no extractable text return:

```json
{"detail":[{"code":"ocr_required","message":"..."}]}
```

## Optional enable

```bash
RAG_OCR_ENABLED=true
# Requires system Tesseract + PyMuPDF get_textpage_ocr — NOT installed in default Docker image
```

When enabled, `extract_pdf_pages` retries via PyMuPDF OCR. Failures return `ocr_failed` (not a silent empty index).

Default Strict/Demo images stay slim. Convert scanned PDFs offline, or run OCR on a dedicated worker image. Cost notes: [COST.md](COST.md) · [PROFILES.md](PROFILES.md).
