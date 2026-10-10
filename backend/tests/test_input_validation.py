"""Audit regressions: invalid user input is rejected with 400 / 404 and never stored (it used to be stored and break
the project with 500s, or silently produce negative costs)."""
from __future__ import annotations

import pytest

from conftest import new_project


@pytest.mark.parametrize("body", [{"qty": -5}, {"rate": -100}, {"qty": "abc"}, {"rate": 1e12}])
def test_item_edits_validated_and_not_stored(env, body):
    _, c = env
    p = new_project(c, {})
    r = c.patch(f"/api/projects/{p['id']}/items/plaster_int", json=body)
    assert r.status_code == 400
    assert c.get(f"/api/projects/{p['id']}").status_code == 200  # project still loads (nothing invalid saved)
    assert c.patch(f"/api/projects/{p['id']}/items/plaster_int", json={"qty": 10}).status_code == 200


@pytest.mark.parametrize("params", [{"floors": "abc"}, {"floor_height": -3}, {"floors": 0}, {"gst": 99}, {"finish": "gold"}])
def test_params_validated(env, params):
    _, c = env
    p = new_project(c, {})
    assert c.patch(f"/api/projects/{p['id']}", json={"params": params}).status_code == 400
    assert c.get(f"/api/projects/{p['id']}").status_code == 200


def test_sheet_index_and_calibration_validated(env):
    _, c = env
    p = new_project(c, {})
    assert c.patch(f"/api/projects/{p['id']}/sheets/99", json={"enabled": False}).status_code == 404
    assert c.patch(f"/api/projects/{p['id']}/sheets/0", json={"calib": {"real_m": 5, "measured_m": 0}}).status_code == 400
    assert c.post(f"/api/projects/{p['id']}/items", json={"description": "x", "qty": -1, "unit": "sqm"}).status_code == 400
