
import re
from datetime import date
from enum import Enum
from typing import Optional

from pydantic import BaseModel, ConfigDict, field_validator, model_validator

US_STATES = {
    "AL", "AK", "AZ", "AR", "CA", "CO", "CT", "DE", "DC", "FL", "GA", "HI", "ID", "IL", "IN",
    "IA", "KS", "KY", "LA", "ME", "MD", "MA", "MI", "MN", "MS", "MO", "MT", "NE", "NV", "NH",
    "NJ", "NM", "NY", "NC", "ND", "OH", "OK", "OR", "PA", "RI", "SC", "SD", "TN", "TX", "UT",
    "VT", "VA", "WA", "WV", "WI", "WY",
}

NAME_RE = re.compile(r"^[A-Za-z][A-Za-z'\- ]*$")
ZIP_RE = re.compile(r"^\d{5}(-\d{4})?$")
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class Sex(str, Enum):
    MALE = "Male"
    FEMALE = "Female"
    OTHER = "Other"
    DECLINE = "Decline to Answer"



def normalize_phone(value: str) -> str:
    digits = re.sub(r"\D", "", str(value))
    if len(digits) == 11 and digits.startswith("1"):
        digits = digits[1:]
    if len(digits) != 10:
        raise ValueError("must be a valid 10-digit U.S. phone number")
    return digits


def parse_dob(value) -> date:
   
    if isinstance(value, date):
        d = value
    else:
        text = str(value).strip()
        try:
            if re.fullmatch(r"\d{1,2}/\d{1,2}/\d{4}", text):
                m, day, y = (int(p) for p in text.split("/"))
                d = date(y, m, day)
            else:
                d = date.fromisoformat(text)
        except ValueError:
            raise ValueError("must be a real date in MM/DD/YYYY format")
    if d > date.today():
        raise ValueError("date of birth cannot be in the future")
    if d.year < 1900:
        raise ValueError("date of birth is too far in the past")
    return d


def _length(v: str, lo: int, hi: int, label: str) -> str:
    if not lo <= len(v) <= hi:
        raise ValueError(f"{label} must be {lo}-{hi} characters")
    return v


class _PatientRules(BaseModel):
  

    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="before")
    @classmethod
    def _sanitize(cls, data):
    
        if not isinstance(data, dict):
            return data
        out = {}
        for k, v in data.items():
            if isinstance(v, str):
                v = re.sub(r"[\x00-\x1f]", " ", v).replace("<", "").replace(">", "")
                v = " ".join(v.split()) or None
            out[k] = v
        return out

    @field_validator("first_name", "last_name", check_fields=False)
    @classmethod
    def _names(cls, v):
        if v is None:
            return v
        _length(v, 1, 50, "name")
        if not NAME_RE.match(v):
            raise ValueError("may only contain letters, hyphens and apostrophes")
        return v

    @field_validator("date_of_birth", mode="before", check_fields=False)
    @classmethod
    def _dob(cls, v):
        return None if v is None else parse_dob(v)

    @field_validator("sex", mode="before", check_fields=False)
    @classmethod
    def _sex(cls, v):
        if v is None:
            return v
        s = str(v).strip().lower()
        if s.startswith("decline") or s in {"prefer not to say", "prefer not to answer"}:
            return Sex.DECLINE
        for option in Sex:
            if option.value.lower() == s:
                return option
        raise ValueError("must be Male, Female, Other, or Decline to Answer")

    @field_validator("phone_number", "emergency_contact_phone", check_fields=False)
    @classmethod
    def _phones(cls, v):
        return None if v is None else normalize_phone(v)

    @field_validator("email", check_fields=False)
    @classmethod
    def _email(cls, v):
        if v is None:
            return v
        v = v.lower().replace(" ", "")
        if len(v) > 254 or not EMAIL_RE.match(v):
            raise ValueError("must be a valid email address")
        return v

    @field_validator("state", check_fields=False)
    @classmethod
    def _state(cls, v):
        if v is None:
            return v
        v = v.upper()
        if v not in US_STATES:
            raise ValueError("must be a valid 2-letter U.S. state abbreviation")
        return v

    @field_validator("zip_code", check_fields=False)
    @classmethod
    def _zip(cls, v):
        if v is None:
            return v
        if not ZIP_RE.match(v):
            raise ValueError("must be a 5-digit ZIP or ZIP+4")
        return v

    @field_validator("city", check_fields=False)
    @classmethod
    def _city(cls, v):
        return v if v is None else _length(v, 1, 100, "city")

    @field_validator("address_line_1", check_fields=False)
    @classmethod
    def _addr1(cls, v):
        return v if v is None else _length(v, 1, 200, "address")

    @field_validator("address_line_2", "insurance_provider", "emergency_contact_name",
                     check_fields=False)
    @classmethod
    def _short_text(cls, v):
        return v if v is None else _length(v, 1, 100, "value")

    @field_validator("insurance_member_id", check_fields=False)
    @classmethod
    def _member_id(cls, v):
        if v is None:
            return v
        v = re.sub(r"[\s\-]", "", v)  # callers often say "dash" or pause between chunks
        if not re.fullmatch(r"[A-Za-z0-9]{1,50}", v):
            raise ValueError("must be alphanumeric")
        return v.upper()

    @field_validator("preferred_language", check_fields=False)
    @classmethod
    def _lang(cls, v):
        return v if v is None else _length(v, 1, 50, "language")


class PatientCreate(_PatientRules):
    first_name: str
    last_name: str
    date_of_birth: date
    sex: Sex
    phone_number: str
    address_line_1: str
    city: str
    state: str
    zip_code: str
    email: Optional[str] = None
    address_line_2: Optional[str] = None
    insurance_provider: Optional[str] = None
    insurance_member_id: Optional[str] = None
    preferred_language: str = "English"
    emergency_contact_name: Optional[str] = None
    emergency_contact_phone: Optional[str] = None


class PatientUpdate(_PatientRules):
  

    first_name: Optional[str] = None
    last_name: Optional[str] = None
    date_of_birth: Optional[date] = None
    sex: Optional[Sex] = None
    phone_number: Optional[str] = None
    address_line_1: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    zip_code: Optional[str] = None
    email: Optional[str] = None
    address_line_2: Optional[str] = None
    insurance_provider: Optional[str] = None
    insurance_member_id: Optional[str] = None
    preferred_language: Optional[str] = None
    emergency_contact_name: Optional[str] = None
    emergency_contact_phone: Optional[str] = None


def format_errors(errors: list) -> list[dict]:

    out = []
    for e in errors:
        field = ".".join(str(x) for x in e["loc"] if x not in ("body",))
        msg = e["msg"].removeprefix("Value error, ")
        if e["type"] == "missing":
            msg = "is required"
        out.append({"field": field, "message": msg})
    return out
