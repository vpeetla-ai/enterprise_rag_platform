# OCR path (Phase 5 — optional)

Scanned PDFs with no extractable text return:

```json
{"detail":[{"code":"ocr_required","message":"..."}]}
```

## Enable later

```bash
RAG_OCR_ENABLED=true
# Provider TBD: ocrmypdf local or cloud OCR — cost labeled in PROFILES.md
```

Until enabled, upload a text-layer PDF or convert offline. Do not silently index empty pages.
