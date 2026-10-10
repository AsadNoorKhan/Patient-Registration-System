# """Voice-agent <-> backend glue.

# Vapi (telephony + STT + TTS + LLM) POSTs to /vapi/webhook. We handle two message types:
#   * tool-calls          -> the LLM asked us to run lookup_patient / save_patient
#   * end-of-call-report  -> logged for observability (transcript + why the call ended)

# Tool results are plain JSON strings the LLM reads. Failures are written as INSTRUCTIONS
# ("ask the caller for X again") so the agent never goes silent on an error.
# The service layer (db.py + schemas.py) is shared with the REST API.
# """
# import hmac
# import json
# import logging
# import os

# from fastapi import APIRouter, HTTPException, Request
# from pydantic import ValidationError

# from . import db
# from .schemas import PatientCreate, PatientUpdate, format_errors

# router = APIRouter()
# log = logging.getLogger("voice")


# def _check_secret(request: Request) -> None:
#     secret = os.getenv("VAPI_SECRET")
#     if secret and not hmac.compare_digest(request.headers.get("x-vapi-secret", ""), secret):
#         raise HTTPException(401, "Invalid webhook secret")


# # ------------------------------------------------------------------ tools
# def lookup_patient(args: dict) -> dict:
#     """Duplicate detection: called right after the caller gives their phone number."""
#     try:
#         patient = db.find_by_phone(args.get("phone_number", ""))
#     except ValueError as e:
#         return {"found": False, "error": f"phone_number {e}. Ask the caller to repeat it."}
#     if not patient:
#         return {"found": False}
#     return {"found": True, "patient_id": patient["patient_id"],
#             "first_name": patient["first_name"], "last_name": patient["last_name"]}


# def save_patient(args: dict) -> dict:
#     """Create a new patient, or update one if patient_id is provided."""
#     patient_id = args.pop("patient_id", None)
#     try:
#         if patient_id:
#             model = PatientUpdate(**args)
#             patient = db.update_patient(patient_id, model.model_dump(mode="json", exclude_unset=True))
#             action = "updated"
#         else:
#             model = PatientCreate(**args)
#             patient = db.create_patient(model.model_dump(mode="json"))
#             action = "created"
#         if not patient:
#             return {"success": False, "instruction": "Apologize: that record could not be found. "
#                     "Offer to register as a new patient."}
#         # Observability requirement: log the final collected payload.
#         log.info("PATIENT_%s payload=%s", action.upper(), json.dumps(patient))
#         return {"success": True, "action": action, "first_name": patient["first_name"],
#                 "patient_id": patient["patient_id"]}
#     except ValidationError as e:
#         errors = format_errors(e.errors())
#         log.info("Validation failed in tool call: %s", errors)
#         return {"success": False, "errors": errors,
#                 "instruction": "Tell the caller what was wrong in plain words and re-ask ONLY "
#                                "for the invalid field(s). Do not re-ask for the rest."}
#     except db.DuplicatePhoneError:
#         return {"success": False, "instruction": "A record with this phone number already exists. "
#                 "Call lookup_patient, then ask if they'd like to update it instead."}
#     except Exception:
#         log.exception("save_patient failed")
#         return {"success": False, "instruction": "Apologize: a technical problem stopped the save. "
#                 "Offer to try once more; if it fails again, tell them to call back shortly."}


# TOOLS = {"lookup_patient": lookup_patient, "save_patient": save_patient}


# def _extract_calls(message: dict):
#     """Vapi payloads vary slightly by version; support both shapes."""
#     calls = [(c.get("id"), c.get("name"), c.get("arguments") or {})
#              for c in message.get("toolCallList") or []]
#     if not calls:
#         for c in message.get("toolCalls") or []:
#             fn = c.get("function", {})
#             args = fn.get("arguments") or {}
#             calls.append((c.get("id"), fn.get("name"), json.loads(args) if isinstance(args, str) else args))
#     return calls


# @router.post("/vapi/webhook")
# async def vapi_webhook(request: Request):
#     _check_secret(request)
#     message = (await request.json()).get("message", {})
#     mtype = message.get("type")

#     if mtype == "tool-calls":
#         results = []
#         for call_id, name, args in _extract_calls(message):
#             handler = TOOLS.get(name)
#             outcome = handler(dict(args)) if handler else {"error": f"unknown tool {name}"}
#             results.append({"toolCallId": call_id, "result": json.dumps(outcome)})
#         return {"results": results}

#     if mtype == "end-of-call-report":
#         log.info("CALL_ENDED reason=%s summary=%s", message.get("endedReason"), message.get("summary"))
#         log.info("TRANSCRIPT %s", (message.get("artifact") or {}).get("transcript"))
#     return {}

"""Voice-agent <-> backend glue.

Vapi (telephony + STT + TTS + LLM) POSTs to /vapi/webhook. We handle two message types:
  * tool-calls          -> the LLM asked us to run lookup_patient / save_patient
  * end-of-call-report  -> logged for observability (transcript + why the call ended)

Tool results are plain JSON strings the LLM reads. Failures are written as INSTRUCTIONS
("ask the caller for X again") so the agent never goes silent on an error.
The service layer (db.py + schemas.py) is shared with the REST API.
"""
import hmac
import json
import logging
import os

from fastapi import APIRouter, HTTPException, Request
from pydantic import ValidationError

from . import db
from .schemas import PatientCreate, PatientUpdate, format_errors

router = APIRouter()
log = logging.getLogger("voice")


def _check_secret(request: Request) -> None:
    secret = os.getenv("VAPI_SECRET")
    if secret and not hmac.compare_digest(request.headers.get("x-vapi-secret", ""), secret):
        raise HTTPException(401, "Invalid webhook secret")


# ------------------------------------------------------------------ tools
def lookup_patient(args: dict) -> dict:
    """Duplicate detection: called right after the caller gives their phone number."""
    try:
        patient = db.find_by_phone(args.get("phone_number", ""))
    except ValueError as e:
        return {"found": False, "error": f"phone_number {e}. Ask the caller to repeat it."}
    if not patient:
        return {"found": False}
    return {"found": True, "patient_id": patient["patient_id"],
            "first_name": patient["first_name"], "last_name": patient["last_name"]}


def save_patient(args: dict) -> dict:
    """Create a new patient, or update one if patient_id is provided."""
    patient_id = args.pop("patient_id", None)
    try:
        if patient_id:
            model = PatientUpdate(**args)
            patient = db.update_patient(patient_id, model.model_dump(mode="json", exclude_unset=True))
            action = "updated"
        else:
            model = PatientCreate(**args)
            patient = db.create_patient(model.model_dump(mode="json"))
            action = "created"
        if not patient:
            return {"success": False, "instruction": "Apologize: that record could not be found. "
                    "Offer to register as a new patient."}
        # Observability requirement: log the final collected payload.
        log.info("PATIENT_%s payload=%s", action.upper(), json.dumps(patient))
        return {"success": True, "action": action, "first_name": patient["first_name"],
                "patient_id": patient["patient_id"]}
    except ValidationError as e:
        errors = format_errors(e.errors())
        log.info("Validation failed in tool call: %s", errors)
        return {"success": False, "errors": errors,
                "instruction": "Tell the caller what was wrong in plain words and re-ask ONLY "
                               "for the invalid field(s). Do not re-ask for the rest."}
    except db.DuplicatePhoneError:
        return {"success": False, "instruction": "A record with this phone number already exists. "
                "Call lookup_patient, then ask if they'd like to update it instead."}
    except Exception:
        log.exception("save_patient failed")
        return {"success": False, "instruction": "Apologize: a technical problem stopped the save. "
                "Offer to try once more; if it fails again, tell them to call back shortly."}


TOOLS = {"lookup_patient": lookup_patient, "save_patient": save_patient}


def _extract_calls(message: dict):
    """Vapi sends {"id", "function": {"name", "arguments"}} (arguments may be a dict or a
    JSON string). Also tolerate the flat {"id", "name", "arguments"} shape."""
    raw = message.get("toolCallList") or message.get("toolCalls") or []
    calls = []
    for c in raw:
        fn = c.get("function") or {}
        name = c.get("name") or fn.get("name")
        args = c.get("arguments") if c.get("arguments") is not None else fn.get("arguments")
        if isinstance(args, str):
            try:
                args = json.loads(args or "{}")
            except json.JSONDecodeError:
                args = {}
        calls.append((c.get("id"), name, args or {}))
    return calls


@router.post("/vapi/webhook")
async def vapi_webhook(request: Request):
    _check_secret(request)
    message = (await request.json()).get("message", {})
    mtype = message.get("type")

    if mtype == "tool-calls":
        results = []
        for call_id, name, args in _extract_calls(message):
            handler = TOOLS.get(name)
            outcome = handler(dict(args)) if handler else {"error": f"unknown tool {name}"}
            results.append({"toolCallId": call_id, "result": json.dumps(outcome)})
        return {"results": results}

    if mtype == "end-of-call-report":
        log.info("CALL_ENDED reason=%s summary=%s", message.get("endedReason"), message.get("summary"))
        log.info("TRANSCRIPT %s", (message.get("artifact") or {}).get("transcript"))
    return {}
