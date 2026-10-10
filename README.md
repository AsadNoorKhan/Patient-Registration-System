# Voice AI Patient Registration Agent

Call a phone number, talk to "Sam", and register as a patient. Data is saved to a database and exposed via a REST API.

## Architecture

```
Caller ──phone──▶  Vapi  (telephony + speech-to-text + LLM + text-to-speech)
                     │  tool calls: lookup_patient / save_patient
                     ▼  HTTPS POST /vapi/webhook
              ┌─────────────────────── FastAPI app ───────────────────────┐
              │ app/vapi.py     voice glue (tool handlers, call logging)  │
              │ app/main.py     REST API (/patients ...) + error envelope │
              │ app/schemas.py  validation rules (shared by both above)   │
              │ app/db.py       SQLite data layer, constraints, soft delete│
              └───────────────────────────────────────────────────────────┘
```

Separation of concerns: telephony and the LLM live in Vapi; the conversation is defined by the prompt (`vapi/system_prompt.md`); validation and persistence live in the backend. The voice webhook and the REST API call the **same** validation + data layer, so rules can't drift.

## Tech stack & why
| Piece | Choice | Why |
|---|---|---|
| Telephony/STT/TTS | Vapi | Real phone number in minutes; lets me spend time on prompt + backend |
| LLM | GPT-4o-mini or Claude (configured in Vapi) | Low latency, good tool use |
| Backend | Python + FastAPI | Typed, fast to write, automatic request parsing |
| Validation | Pydantic v2 | Declarative rules, clear per-field error messages |
| DB | SQLite | Zero setup, persists to a file; CHECK constraints + partial unique index |

## Run locally
```bash
python -m venv .venv && source .venv/bin/activate     # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env                                  # then edit values
export $(grep -v '^#' .env | sed 's/ *#.*//' | xargs) # loads env vars (or set them manually)
uvicorn app.main:app --reload --port 8000
pytest                                                # run the tests
```
Interactive API docs: http://localhost:8000/docs

To let Vapi reach your laptop: `ngrok http 8000` and use the https URL it prints.

## Environment variables
| Name | Purpose | Default |
|---|---|---|
| `VAPI_SECRET` | Shared secret; Vapi must send it as header `x-vapi-secret`. If unset, the webhook is open (dev only). | unset |
| `DB_PATH` | SQLite file location. **Point at a persistent volume in production.** | `data/patients.db` |
| `SEED_DEMO` | `true` inserts one demo patient on first start | `false` |

No API keys are in the source. The Vapi/LLM keys live only in the Vapi dashboard.

## Deploy (Railway )
1. In Railway: New Project → Deploy from GitHub repo.
2. Start command: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
3. Add a **Volume** mounted at `/data` and set `DB_PATH=/data/patients.db` (without this the DB is wiped on redeploy).
4. Set `VAPI_SECRET`. Generate a public domain and check `/health`.

## Set up the Vapi assistant
1. Create a Vapi account → **Tools** → create two Function tools from `vapi/tools.json` (`lookup_patient`, `save_patient`). For each: Server URL = `https://YOUR-HOST/vapi/webhook`, header `x-vapi-secret: <VAPI_SECRET>`.
2. **Assistants** → new blank assistant:
   - Model: GPT-4o-mini (or similar) and paste `vapi/system_prompt.md` (below the `---` line) as the system prompt.
   - First message: `Hi, thanks for calling Riverside Family Clinic, this is Sam. I can get you registered as a new patient — can I start with your first and last name?`
   - Attach both tools, plus Vapi's built-in **End Call** tool.
   - Server URL (assistant level) = `https://YOUR-HOST/vapi/webhook`, with server messages `tool-calls` and `end-of-call-report` enabled.
   - Transcriber: Deepgram (set to multilingual if you want Spanish).
3. **Phone Numbers** → create a free Vapi US number → assign the assistant. Call it!

## API
All responses use `{ "data": ..., "error": null }` (errors: `{ "data": null, "error": { "message", "details" } }`).

| Method | Path | Notes |
|---|---|---|
| GET | `/patients` | Optional `?last_name=&date_of_birth=&phone_number=` |
| GET | `/patients/{id}` | 400 invalid UUID, 404 not found |
| POST | `/patients` | 201; 422 validation; 409 duplicate phone |
| PUT | `/patients/{id}` | Partial update |
| DELETE | `/patients/{id}` | Soft delete (sets `deleted_at`) |
| GET | `/health` | Liveness check |


## Prompt engineering
See `vapi/system_prompt.md` 
## Edge cases
| Situation | Behaviour |
|---|---|
| Invalid DOB / phone / state / ZIP | Webhook returns the failing field + instruction; agent re-asks just that field. API returns 422 |
| Caller corrects a value | Prompt: latest value wins; re-confirm before saving |
| "Start over" | Prompt instructs discarding collected data |
| DB write fails | Tool returns an apology instruction (retry once, then ask caller to call back); error is logged |
| Call drops mid-call | Nothing is saved (we only write after confirmation); `end-of-call-report` is logged with the end reason |
| Existing phone number | `lookup_patient` → offer to update; DB unique index also blocks duplicates (409) |
| Webhook spoofing | `x-vapi-secret` header checked in constant time |
