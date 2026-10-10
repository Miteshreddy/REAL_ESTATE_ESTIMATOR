"""Where Tamil Nadu PWD documents are published.

host_kind tells how much a host is trusted:
  official   — a Government of Tamil Nadu domain (*.tn.gov.in / *.gov.in)
  secondary  — a public non-government host (e.g. the TN PWD engineers' association) re-publishing department
               documents. A file from a secondary host is only 'cross-verified' when the identical file (same SHA-256)
               is also found on an independent host, and it is never labelled 'official'.
"""
from __future__ import annotations

from urllib.parse import urlparse

DISCOVERY_PAGES = [
    dict(url="https://tnpwdea.org/downloads.php?category_id=4", kind="table",
         note="TN PWD Engineers' Association — downloads (SOR, amendments, Standard Data Book)"),
]

# Known direct copies of documents (used for cross-verification by hash; not crawled)
KNOWN_COPIES = [
    dict(url="http://tnebes.org/archive/2025/Jul/SCHEDULE%20OF%20RATES%202025-2026%20-%20VOL%20I.pdf",
         title="Schedule of Rates 2025-2026 Vol I", sha256="0cee169bde79524e6cc34a76266dc5b5a408691c62c4fd69d7a8857eefb49e90"),
]

AUTHORITY = "Tamil Nadu Public Works Department"
DEPARTMENT = "Public Works Department, Government of Tamil Nadu"


def host_kind(url: str) -> str:
    h = (urlparse(url).hostname or "").lower()
    return "official" if h.endswith(".gov.in") or h.endswith(".nic.in") else "secondary"
