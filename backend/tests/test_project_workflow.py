"""Project-first workflow: create a project (details + location) without drawings, then upload drawings into it."""
from __future__ import annotations

import os


def test_create_project_then_upload(env):
    A, c = env
    r = c.post("/api/projects", data=dict(name="Hostel Block A", client="SIPCOT", building_type="Hostel", site_address="Sriperumbudur",
                                          description="G+2", loc='{"district": "Kancheepuram"}'))
    assert r.status_code == 200, r.text
    p = r.json()
    assert p["sheets"] == [] and p["estimate"]["total"] == 0
    assert p["details"] == dict(client="SIPCOT", building_type="Hostel", site_address="Sriperumbudur", description="G+2")
    assert c.get(f"/api/projects/{p['id']}/uploads").json() == []
    lst = next(x for x in c.get("/api/projects").json() if x["id"] == p["id"])
    assert lst["details"]["building_type"] == "Hostel" and lst["files"] == 0
    q = c.patch(f"/api/projects/{p['id']}", json=dict(details=dict(description="G+3 hostel"))).json()
    assert q["details"]["description"] == "G+3 hostel" and q["details"]["client"] == "SIPCOT"
    with open(os.path.join(A.SAMPLES, "villa_g1.dxf"), "rb") as f:
        u = c.post(f"/api/projects/{p['id']}/files", files={"files": ("villa_g1.dxf", f.read())})
    assert u.status_code == 200 and u.json()["sheets"] and u.json()["estimate"]["total"] > 0
    up = c.get(f"/api/projects/{p['id']}/uploads").json()
    assert [x["file"] for x in up] == ["villa_g1.dxf"] and up[0]["sheets"] >= 1
    assert c.get(f"/api/projects/{p['id']}").json()["details"]["description"] == "G+3 hostel"  # stored with the project


def test_project_name_required(env):
    _, c = env
    assert c.post("/api/projects", data=dict(name="   ")).status_code == 400
