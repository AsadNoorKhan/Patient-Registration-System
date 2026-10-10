# import json

# import pytest
# from fastapi.testclient import TestClient

# VALID = {
#     "first_name": "Jane", "last_name": "O'Doe-Smith", "date_of_birth": "03/04/1990",
#     "sex": "female", "phone_number": "(555) 123-4567", "address_line_1": "12 Oak St",
#     "city": "Springfield", "state": "il", "zip_code": "62701",
# }


# @pytest.fixture
# def client(tmp_path, monkeypatch):
#     monkeypatch.setenv("DB_PATH", str(tmp_path / "test.db"))
#     monkeypatch.delenv("VAPI_SECRET", raising=False)
#     from app.main import app
#     with TestClient(app) as c:  # context manager runs startup -> creates tables
#         yield c


# def test_create_normalizes_and_returns_201(client):
#     r = client.post("/patients", json=VALID)
#     assert r.status_code == 201
#     body = r.json()
#     assert body["error"] is None
#     d = body["data"]
#     assert d["phone_number"] == "5551234567" and d["state"] == "IL" and d["sex"] == "Female"
#     assert d["date_of_birth"] == "03/04/1990" and d["patient_id"]


# @pytest.mark.parametrize("field,value", [
#     ("date_of_birth", "01/01/2999"),   # future
#     ("phone_number", "123"),           # too short
#     ("state", "ZZ"),                   # not a state
#     ("zip_code", "1234"),              # bad zip
#     ("first_name", "J4ne"),            # digits in name
# ])
# def test_invalid_input_returns_422(client, field, value):
#     r = client.post("/patients", json={**VALID, field: value})
#     assert r.status_code == 422
#     assert r.json()["data"] is None
#     assert r.json()["error"]["details"][0]["field"] == field


# def test_missing_required_field_422(client):
#     payload = {k: v for k, v in VALID.items() if k != "city"}
#     assert client.post("/patients", json=payload).status_code == 422


# def test_duplicate_phone_409(client):
#     client.post("/patients", json=VALID)
#     assert client.post("/patients", json=VALID).status_code == 409


# def test_get_update_delete_flow(client):
#     pid = client.post("/patients", json=VALID).json()["data"]["patient_id"]
#     assert client.get(f"/patients/{pid}").status_code == 200

#     r = client.put(f"/patients/{pid}", json={"last_name": "Davis"})  # partial update
#     assert r.status_code == 200 and r.json()["data"]["last_name"] == "Davis"
#     assert r.json()["data"]["first_name"] == "Jane"

#     assert client.delete(f"/patients/{pid}").status_code == 200
#     assert client.get(f"/patients/{pid}").status_code == 404      # soft-deleted = hidden
#     assert client.get("/patients").json()["data"] == []


# def test_bad_uuid_400_and_unknown_404(client):
#     assert client.get("/patients/not-a-uuid").status_code == 400
#     assert client.get("/patients/00000000-0000-0000-0000-000000000000").status_code == 404


# def test_list_filters(client):
#     client.post("/patients", json=VALID)
#     assert len(client.get("/patients?last_name=o'doe-smith").json()["data"]) == 1
#     assert len(client.get("/patients?phone_number=555-123-4567").json()["data"]) == 1
#     assert len(client.get("/patients?date_of_birth=03/04/1990").json()["data"]) == 1
#     assert client.get("/patients?last_name=Nobody").json()["data"] == []
#     assert client.get("/patients?date_of_birth=garbage").status_code == 422


# def _tool_call(client, name, args):
#     payload = {"message": {"type": "tool-calls",
#                            "toolCallList": [{"id": "t1", "name": name, "arguments": args}]}}
#     r = client.post("/vapi/webhook", json=payload)
#     assert r.status_code == 200
#     return json.loads(r.json()["results"][0]["result"])


# def test_voice_save_then_lookup_then_update(client):
#     saved = _tool_call(client, "save_patient", dict(VALID))
#     assert saved["success"] and saved["first_name"] == "Jane"

#     found = _tool_call(client, "lookup_patient", {"phone_number": "5551234567"})
#     assert found["found"] and found["last_name"] == "O'Doe-Smith"

#     upd = _tool_call(client, "save_patient", {"patient_id": found["patient_id"], "city": "Chicago"})
#     assert upd["success"] and upd["action"] == "updated"
#     assert client.get(f"/patients/{found['patient_id']}").json()["data"]["city"] == "Chicago"


# def test_voice_validation_error_is_actionable(client):
#     res = _tool_call(client, "save_patient", {**VALID, "date_of_birth": "01/01/2999"})
#     assert res["success"] is False
#     assert res["errors"][0]["field"] == "date_of_birth"
#     assert "re-ask" in res["instruction"]


# def test_webhook_secret_enforced(client, monkeypatch):
#     monkeypatch.setenv("VAPI_SECRET", "s3cret")
#     body = {"message": {"type": "status-update"}}
#     assert client.post("/vapi/webhook", json=body).status_code == 401
#     assert client.post("/vapi/webhook", json=body, headers={"x-vapi-secret": "s3cret"}).status_code == 200


import json

import pytest
from fastapi.testclient import TestClient

VALID = {
    "first_name": "Jane", "last_name": "O'Doe-Smith", "date_of_birth": "03/04/1990",
    "sex": "female", "phone_number": "(555) 123-4567", "address_line_1": "12 Oak St",
    "city": "Springfield", "state": "il", "zip_code": "62701",
}


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("DB_PATH", str(tmp_path / "test.db"))
    monkeypatch.delenv("VAPI_SECRET", raising=False)
    from app.main import app
    with TestClient(app) as c:  # context manager runs startup -> creates tables
        yield c


def test_create_normalizes_and_returns_201(client):
    r = client.post("/patients", json=VALID)
    assert r.status_code == 201
    body = r.json()
    assert body["error"] is None
    d = body["data"]
    assert d["phone_number"] == "5551234567" and d["state"] == "IL" and d["sex"] == "Female"
    assert d["date_of_birth"] == "03/04/1990" and d["patient_id"]


@pytest.mark.parametrize("field,value", [
    ("date_of_birth", "01/01/2999"),   # future
    ("phone_number", "123"),           # too short
    ("state", "ZZ"),                   # not a state
    ("zip_code", "1234"),              # bad zip
    ("first_name", "J4ne"),            # digits in name
])
def test_invalid_input_returns_422(client, field, value):
    r = client.post("/patients", json={**VALID, field: value})
    assert r.status_code == 422
    assert r.json()["data"] is None
    assert r.json()["error"]["details"][0]["field"] == field


def test_missing_required_field_422(client):
    payload = {k: v for k, v in VALID.items() if k != "city"}
    assert client.post("/patients", json=payload).status_code == 422


def test_duplicate_phone_409(client):
    client.post("/patients", json=VALID)
    assert client.post("/patients", json=VALID).status_code == 409


def test_get_update_delete_flow(client):
    pid = client.post("/patients", json=VALID).json()["data"]["patient_id"]
    assert client.get(f"/patients/{pid}").status_code == 200

    r = client.put(f"/patients/{pid}", json={"last_name": "Davis"})  # partial update
    assert r.status_code == 200 and r.json()["data"]["last_name"] == "Davis"
    assert r.json()["data"]["first_name"] == "Jane"

    assert client.delete(f"/patients/{pid}").status_code == 200
    assert client.get(f"/patients/{pid}").status_code == 404      # soft-deleted = hidden
    assert client.get("/patients").json()["data"] == []


def test_bad_uuid_400_and_unknown_404(client):
    assert client.get("/patients/not-a-uuid").status_code == 400
    assert client.get("/patients/00000000-0000-0000-0000-000000000000").status_code == 404


def test_list_filters(client):
    client.post("/patients", json=VALID)
    assert len(client.get("/patients?last_name=o'doe-smith").json()["data"]) == 1
    assert len(client.get("/patients?phone_number=555-123-4567").json()["data"]) == 1
    assert len(client.get("/patients?date_of_birth=03/04/1990").json()["data"]) == 1
    assert client.get("/patients?last_name=Nobody").json()["data"] == []
    assert client.get("/patients?date_of_birth=garbage").status_code == 422


def _tool_call(client, name, args):
    # Real Vapi shape: name/arguments are nested under "function" (captured from a live call).
    payload = {"message": {"type": "tool-calls",
                           "toolCallList": [{"id": "t1", "type": "function",
                                             "function": {"name": name, "arguments": args}}]}}
    r = client.post("/vapi/webhook", json=payload)
    assert r.status_code == 200
    return json.loads(r.json()["results"][0]["result"])


def test_voice_save_then_lookup_then_update(client):
    saved = _tool_call(client, "save_patient", dict(VALID))
    assert saved["success"] and saved["first_name"] == "Jane"

    found = _tool_call(client, "lookup_patient", {"phone_number": "5551234567"})
    assert found["found"] and found["last_name"] == "O'Doe-Smith"

    upd = _tool_call(client, "save_patient", {"patient_id": found["patient_id"], "city": "Chicago"})
    assert upd["success"] and upd["action"] == "updated"
    assert client.get(f"/patients/{found['patient_id']}").json()["data"]["city"] == "Chicago"


def test_voice_validation_error_is_actionable(client):
    res = _tool_call(client, "save_patient", {**VALID, "date_of_birth": "01/01/2999"})
    assert res["success"] is False
    assert res["errors"][0]["field"] == "date_of_birth"
    assert "re-ask" in res["instruction"]


def test_webhook_secret_enforced(client, monkeypatch):
    monkeypatch.setenv("VAPI_SECRET", "s3cret")
    body = {"message": {"type": "status-update"}}
    assert client.post("/vapi/webhook", json=body).status_code == 401
    assert client.post("/vapi/webhook", json=body, headers={"x-vapi-secret": "s3cret"}).status_code == 200