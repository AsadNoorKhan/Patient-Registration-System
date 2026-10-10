
import os
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import date, datetime, timezone
from typing import Optional

from .schemas import normalize_phone, parse_dob

SCHEMA = """
CREATE TABLE IF NOT EXISTS patients (
    patient_id              TEXT PRIMARY KEY,
    first_name              TEXT NOT NULL CHECK (length(first_name) BETWEEN 1 AND 50),
    last_name               TEXT NOT NULL CHECK (length(last_name) BETWEEN 1 AND 50),
    date_of_birth           TEXT NOT NULL CHECK (date_of_birth GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]'),
    sex                     TEXT NOT NULL CHECK (sex IN ('Male','Female','Other','Decline to Answer')),
    phone_number            TEXT NOT NULL CHECK (length(phone_number) = 10 AND phone_number NOT GLOB '*[^0-9]*'),
    email                   TEXT,
    address_line_1          TEXT NOT NULL,
    address_line_2          TEXT,
    city                    TEXT NOT NULL CHECK (length(city) BETWEEN 1 AND 100),
    state                   TEXT NOT NULL CHECK (length(state) = 2),
    zip_code                TEXT NOT NULL CHECK (length(zip_code) IN (5, 10)),
    insurance_provider      TEXT,
    insurance_member_id     TEXT,
    preferred_language      TEXT NOT NULL DEFAULT 'English',
    emergency_contact_name  TEXT,
    emergency_contact_phone TEXT CHECK (emergency_contact_phone IS NULL OR
                              (length(emergency_contact_phone) = 10 AND emergency_contact_phone NOT GLOB '*[^0-9]*')),
    created_at              TEXT NOT NULL,
    updated_at              TEXT NOT NULL,
    deleted_at              TEXT            -- soft delete: NULL = active
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_patients_phone_active
    ON patients(phone_number) WHERE deleted_at IS NULL;
CREATE INDEX IF NOT EXISTS idx_patients_last_name ON patients(last_name COLLATE NOCASE);
CREATE INDEX IF NOT EXISTS idx_patients_dob ON patients(date_of_birth);
"""

NOT_NULL_FIELDS = {"first_name", "last_name", "date_of_birth", "sex", "phone_number",
                   "address_line_1", "city", "state", "zip_code", "preferred_language"}
UPDATABLE_FIELDS = NOT_NULL_FIELDS | {"email", "address_line_2", "insurance_provider",
                                      "insurance_member_id", "emergency_contact_name",
                                      "emergency_contact_phone"}


class DuplicatePhoneError(Exception):
    """Raised when an active patient already has this phone number."""


def db_path() -> str:
   
    path = os.getenv("DB_PATH", "data/patients.db")
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    return path


@contextmanager
def get_conn():
    conn = sqlite3.connect(db_path())
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _to_api(row: sqlite3.Row) -> dict:
    d = dict(row)
    d["date_of_birth"] = date.fromisoformat(d["date_of_birth"]).strftime("%m/%d/%Y")
    return d


def init_db() -> None:
    with get_conn() as conn:
        conn.executescript(SCHEMA)
        if os.getenv("SEED_DEMO") == "true":
            if conn.execute("SELECT COUNT(*) FROM patients").fetchone()[0] == 0:
                now = _now()
                conn.execute(
                    "INSERT INTO patients (patient_id, first_name, last_name, date_of_birth, sex,"
                    " phone_number, address_line_1, city, state, zip_code, created_at, updated_at)"
                    " VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                    (str(uuid.uuid4()), "Alex", "Example", "1985-06-15", "Other", "5555550100",
                     "100 Demo Street", "Springfield", "IL", "62701", now, now),
                )


def _translate_integrity(e: sqlite3.IntegrityError):
    if "phone_number" in str(e):
        raise DuplicatePhoneError("A patient with this phone number already exists") from e
    raise e


def create_patient(data: dict) -> dict:
    row = {**data, "patient_id": str(uuid.uuid4()), "created_at": _now(), "updated_at": _now()}
    cols = ", ".join(row)
    placeholders = ", ".join("?" for _ in row)
    try:
        with get_conn() as conn:
            conn.execute(f"INSERT INTO patients ({cols}) VALUES ({placeholders})", list(row.values()))
    except sqlite3.IntegrityError as e:
        _translate_integrity(e)
    return get_patient(row["patient_id"])


def get_patient(patient_id: str) -> Optional[dict]:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM patients WHERE patient_id = ? AND deleted_at IS NULL", (patient_id,)
        ).fetchone()
    return _to_api(row) if row else None


def find_by_phone(phone: str) -> Optional[dict]:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM patients WHERE phone_number = ? AND deleted_at IS NULL",
            (normalize_phone(phone),),
        ).fetchone()
    return _to_api(row) if row else None


def list_patients(last_name=None, date_of_birth=None, phone_number=None) -> list[dict]:
    clauses, params = ["deleted_at IS NULL"], []
    if last_name:
        clauses.append("last_name = ? COLLATE NOCASE")
        params.append(last_name.strip())
    if date_of_birth:
        clauses.append("date_of_birth = ?")
        params.append(parse_dob(date_of_birth).isoformat())  # ValueError -> 422 in the API
    if phone_number:
        clauses.append("phone_number = ?")
        params.append(normalize_phone(phone_number))
    with get_conn() as conn:
        rows = conn.execute(
            f"SELECT * FROM patients WHERE {' AND '.join(clauses)} ORDER BY created_at DESC", params
        ).fetchall()
    return [_to_api(r) for r in rows]


def update_patient(patient_id: str, fields: dict) -> Optional[dict]:
    
    fields = {k: v for k, v in fields.items()
              if k in UPDATABLE_FIELDS and not (v is None and k in NOT_NULL_FIELDS)}
    if not get_patient(patient_id):
        return None
    if fields:
        sets = ", ".join(f"{k} = ?" for k in fields) + ", updated_at = ?"
        try:
            with get_conn() as conn:
                conn.execute(
                    f"UPDATE patients SET {sets} WHERE patient_id = ? AND deleted_at IS NULL",
                    [*fields.values(), _now(), patient_id],
                )
        except sqlite3.IntegrityError as e:
            _translate_integrity(e)
    return get_patient(patient_id)


def soft_delete_patient(patient_id: str) -> bool:
    with get_conn() as conn:
        cur = conn.execute(
            "UPDATE patients SET deleted_at = ?, updated_at = ? "
            "WHERE patient_id = ? AND deleted_at IS NULL",
            (_now(), _now(), patient_id),
        )
    return cur.rowcount > 0
