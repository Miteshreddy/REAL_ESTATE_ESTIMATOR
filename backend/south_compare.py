"""Same drawing priced under each south-Indian schedule (+ CPWD): quantities must be identical, only rates differ.
Projects are created in the real database and deleted afterwards. AP needs user cement/steel rates (it prints none);
the values used here are TEST INPUTS, labelled as such in the output.
Usage: python south_compare.py [sample]"""
import json
import os
import sys

from fastapi.testclient import TestClient

import app as A

SAMPLE = sys.argv[1] if len(sys.argv) > 1 else "compact_home.dxf"
RUNS = [("CPWD DSR 2023", "in-cpwd-dsr-2023-civil", {}),
        ("Telangana Z1", "india-telangana-telangana-r-b-department-sor-2026-27", {"labour_zone": "Z1"}),
        ("Telangana Z3", "india-telangana-telangana-r-b-department-sor-2026-27", {"labour_zone": "Z3"}),
        ("Andhra Pradesh*", "india-andhra-pradesh-andhra-pradesh-r-b-department-sor-2025-26", {"cement_rate": 7000, "steel_rate": 65000}),
        ("Tamil Nadu", "india-tamil-nadu-tamil-nadu-pwd-sor-2025-26", {}),
        ("Karnataka", "india-karnataka-karnataka-pwd-sr-2023-24", {}),
        ("Kerala (adopts CPWD)", "india-kerala-kerala-pwd-dsr-adopted-2023", {}),
        ("Puducherry", "india-puducherry-puducherry-puducherry-pwd-psr-2024-25", {})]

out = []
with TestClient(A.app) as c:
    q0 = None
    for name, sid, params in RUNS:
        p = c.post("/api/projects", data=dict(name="south-compare", sample=SAMPLE, loc="{}", rate_schedule_id=sid)).json()
        if params:
            p = c.patch(f"/api/projects/{p['id']}", json=dict(params=params)).json()
        e = p["estimate"]
        q = {i["key"]: i["qty"] for i in e["items"]}
        q0 = q0 or q
        cats = {x["name"]: round(x["amount"]) for x in e["categories"]}
        area = p.get("summary", {}).get("built_up") or p["stats"].get("built_up_area") or 0
        out.append(dict(schedule=name, total=round(e["total"]), same_quantities=q == q0, priced=sum(1 for i in e["items"] if i["rate"] is not None),
                        excluded=len(e.get("excluded", [])), excluded_items=[x["description"][:50] for x in e.get("excluded", [])], categories=cats,
                        test_inputs=params or None))
        c.delete(f"/api/projects/{p['id']}")
        print(name, out[-1]["total"], out[-1]["same_quantities"], "excluded", out[-1]["excluded"], flush=True)
json.dump(dict(sample=SAMPLE, runs=out, note="* AP cement ₹7,000/t and steel ₹65,000/t are TEST INPUTS (AP SOR prints no cement/steel rate)"),
          open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "south_compare.json"), "w"), indent=1)
