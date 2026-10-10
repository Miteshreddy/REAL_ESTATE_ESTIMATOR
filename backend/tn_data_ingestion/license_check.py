"""Source / licence status of a file. A public web page is NOT an ML-training licence: anything not clearly cleared
goes to REVIEW. Statuses: cleared | government_publication_review | client_permission | disallowed | review."""
from __future__ import annotations

from urllib.parse import urlparse

from .source_registry import SOURCES


def status(source_id: str | None, url: str | None = None, robots_allowed: bool | None = None) -> dict:
    if robots_allowed is False:
        return dict(status="disallowed", reason="robots.txt disallows this URL — not downloaded")
    src = next((s for s in SOURCES if s["id"] == source_id), None)
    if src is None and url:
        host = (urlparse(url).hostname or "").lower()
        src = next((s for s in SOURCES if s["url"] and urlparse(s["url"]).hostname == host), None)
    if src is None:
        return dict(status="review", reason="unknown source — manual licence review required before any use")
    if src["kind"] in ("third_party_copyright", "non_tn"):
        return dict(status="restricted", reason=src["note"])
    if src["kind"] == "client":
        return dict(status="client_permission", reason="provided by the client / user")
    if src["kind"] == "government":
        return dict(status="government_publication_review",
                    reason="public Government document — usable for internal evaluation; training use pending licence confirmation")
    return dict(status="review", reason=src["note"])


def usable_for(lic: str, purpose: str) -> bool:
    if lic in ("disallowed", "review", "restricted"):
        return purpose in ("SMOKE_TEST", "REFERENCE") and lic == "restricted"
    if purpose in ("06_VALIDATION", "07_UNSEEN_TEST", "04_PWD_KNOWLEDGE"):
        return True
    return lic in ("cleared", "client_permission")  # government publications: evaluation only until licence is confirmed
