"""Tamil Nadu construction-drawing data ingestion (for the TN drawing DATASET — not for pricing).

    discover (robots.txt) → download (timeouts, retries, magic bytes, SHA-256) → licence / source status
    → classify (drawing type, discipline) → parse (text, OCR, tables, pages) → metadata (district, building type)
    → dedup (SHA-256, perceptual hash, OCR similarity) → project grouping → dataset purpose folders
    → annotation queue (pseudo labels kept separate from verified labels)

Nothing ingested here is training data until its licence status is cleared AND its annotations are verified.
Unclear sources go to DISCOVERY / REVIEW.
"""
VERSION = "tndata-1.0.0"
