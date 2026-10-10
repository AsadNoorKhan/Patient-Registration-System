"""REST API. Run with: uvicorn app.main:app --reload"""
import logging
import uuid
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI, HTTPException, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from . import db
from .schemas import PatientCreate, PatientUpdate, format_errors
from .vapi import router as vapi_router

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("api")


@asynccontextmanager
async def lifespan(_: FastAPI):
    db.init_db()
    yield


app = FastAPI(title="Patient Registration API", lifespan=lifespan)
app.include_router(vapi_router)


# ---------- consistent envelope: {"data": ..., "error": ...} ----------
def ok(data, status: int = 200) -> JSONResponse:
    return JSONResponse(status_code=status, content={"data": jsonable_encoder(data), "error": None})


def fail(status: int, message: str, details=None) -> JSONResponse:
    return JSONResponse(status_code=status, content={
        "data": None, "error": {"message": message, "details": jsonable_encoder(details)}})


@app.exception_handler(RequestValidationError)
async def on_validation_error(_: Request, exc: RequestValidationError):
    if any(e["type"] == "json_invalid" for e in exc.errors()):
        return fail(400, "Malformed JSON body")
    return fail(422, "Validation failed", format_errors(exc.errors()))


@app.exception_handler(StarletteHTTPException)
async def on_http_error(_: Request, exc: StarletteHTTPException):
    return fail(exc.status_code, str(exc.detail))


@app.exception_handler(Exception)
async def on_unexpected(_: Request, exc: Exception):
    log.exception("Unhandled error")
    return fail(500, "Internal server error")  # never leak internals


def _check_uuid(patient_id: str) -> str:
    try:
        uuid.UUID(patient_id)
    except ValueError:
        raise HTTPException(400, "patient_id must be a valid UUID")
    return patient_id


# ---------- routes ----------
@app.get("/health")
def health():
    return ok({"status": "ok"})


@app.get("/patients")
def list_patients(last_name: Optional[str] = None, date_of_birth: Optional[str] = None,
                  phone_number: Optional[str] = None):
    try:
        return ok(db.list_patients(last_name, date_of_birth, phone_number))
    except ValueError as e:
        return fail(422, "Invalid filter", str(e))


@app.get("/patients/{patient_id}")
def get_patient(patient_id: str):
    patient = db.get_patient(_check_uuid(patient_id))
    if not patient:
        raise HTTPException(404, "Patient not found")
    return ok(patient)


@app.post("/patients")
def create_patient(payload: PatientCreate):
    try:
        patient = db.create_patient(payload.model_dump(mode="json"))
    except db.DuplicatePhoneError as e:
        return fail(409, str(e))
    return ok(patient, 201)


@app.put("/patients/{patient_id}")
def update_patient(patient_id: str, payload: PatientUpdate):
    fields = payload.model_dump(mode="json", exclude_unset=True)
    if not fields:
        raise HTTPException(400, "No fields to update")
    try:
        patient = db.update_patient(_check_uuid(patient_id), fields)
    except db.DuplicatePhoneError as e:
        return fail(409, str(e))
    if not patient:
        raise HTTPException(404, "Patient not found")
    return ok(patient)


@app.delete("/patients/{patient_id}")
def delete_patient(patient_id: str):
    if not db.soft_delete_patient(_check_uuid(patient_id)):
        raise HTTPException(404, "Patient not found")
    return ok({"patient_id": patient_id, "deleted": True})
