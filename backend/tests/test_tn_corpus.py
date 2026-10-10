"""TN drawing-corpus pipeline guards (tn_corpus/scripts). No network: robots/DNS are stubbed."""
from __future__ import annotations

import os
import sys

import pytest

SCRIPTS = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "tn_corpus", "scripts")
sys.path.insert(0, SCRIPTS)
import safe_fetch as sf  # noqa: E402
import tnrd_discover as td  # noqa: E402


@pytest.mark.parametrize("url", ["file:///etc/passwd", "ftp://tnrd.tn.gov.in/x.pdf", "http://127.0.0.1/x", "https://evil.example.com/a.pdf"])
def test_ssrf_and_allowlist_reject(url):
    assert sf.ssrf_ok(url)[0] is False


def test_private_resolution_rejected(monkeypatch):
    monkeypatch.setattr(sf.socket, "getaddrinfo", lambda *a, **k: [(0, 0, 0, "", ("10.0.0.5", 443))])
    ok, why = sf.ssrf_ok("https://tnrd.tn.gov.in/buildings_design.html")
    assert not ok and "non-public" in why


def test_robots_wildcards_and_kill_switch(monkeypatch, tmp_path):
    sf._robots["https://rera.tn.gov.in"] = ([], ["/uploads/", "/*.pdf$"])
    assert not sf.robots_allowed("https://rera.tn.gov.in/a/b/plan.pdf")
    assert sf.robots_allowed("https://rera.tn.gov.in/a/b/plan.html")
    sf._robots["https://tnrd.tn.gov.in"] = ([], ["/rdweb_newsite/"])
    assert not sf.robots_allowed("https://tnrd.tn.gov.in/rdweb_newsite/project/reports/Public/WebsitePolicies.php")
    assert sf.robots_allowed("https://tnrd.tn.gov.in/buildings_design/1.ESB-Model.pdf")
    kill = tmp_path / "STOP"
    kill.write_text("stop")
    monkeypatch.setattr(sf, "KILL", str(kill))
    monkeypatch.setattr(sf, "LOG", str(tmp_path / "log.jsonl"))
    with pytest.raises(sf.Blocked):
        sf.check("https://tnrd.tn.gov.in/buildings_design.html")
    assert "kill switch" in (tmp_path / "log.jsonl").read_text()


def test_catalogue_parser_keeps_titles_and_dedupes():
    html = ('<table><tr><td><a href="buildings_design/3.Anganwadi-Model.pdf">Anganwadi Building</a></td>'
            '<td><a href="buildings_design/Beam L.S-3.pdf">Beam L.S-3</a></td></tr>'
            '<tr><td><a href="buildings_design/3.Anganwadi-Model.pdf">Anganwadi Building</a></td></tr></table>')
    rows = td.parse_catalog(html)
    assert len(rows) == 2 and rows[0]["category_hint"] == "anganwadi"
    assert rows[1]["set_hint"].startswith("INFERRED") and rows[0]["url"].startswith("https://tnrd.tn.gov.in/buildings_design/")


def test_page_classifier_and_no_auto_approval():
    import build_corpus as bc
    assert bc.classify("", 0, 0.0, 0.0)[0] == "blank_unknown"
    assert bc.classify("FOUNDATION PLAN footing F1", 400, 0.08, 0)[0] == "foundation"
    assert bc.classify("GROUND FLOOR PLAN kitchen", 400, 0.08, 0)[0] == "architectural_floor_plan"
    assert bc.classify("word " * 400, 10, 0.05, 0)[0] == "unrelated_text"
    assert "selling_price" in open(os.path.join(SCRIPTS, "build_corpus.py"), encoding="utf-8").read()  # schema forbids selling price as cost


def test_pii_screen_flags_patient_records_not_drawings():
    import build_corpus as bc
    assert bc.pii_suspected("Patient Name : X   Age/Sex : 37 Years / Male   Referring Doctor")
    assert bc.pii_suspected("Aadhaar No. 2345 6789 0123")
    assert not bc.pii_suspected("3000 4500 1200 2300 230 115")  # dimension runs on drawings are not identity numbers
    assert not bc.pii_suspected("GROUND FLOOR PLAN  BED ROOM 3000 X 3600  SCALE 1:100  TYPICAL FLOOR PLAN")
