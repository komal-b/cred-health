
# Credo Health Take-Home — Patient Migration
 
Fetches Patient and Observation data from the public HAPI FHIR sandbox
(`https://hapi.fhir.org/baseR4`), transforms it into a simplified
internal schema, stores it in SQLite, and exposes a small read-only
REST API with a Vue frontend to browse migrated patients, search by
FHIR ID, and view their observations.
 
See `Plan.md` for the full production-scale migration plan (Part 1).
This repo is the working slice described in Part 2, deliberately
simpler in scope, see "Where this differs from Plan.md" below.
 
## Setup & Run
 
Requires Docker and Docker Compose. No local Python or Node setup needed.
 
```bash
docker compose up --build
```
 
That's it. This single command:
1. Builds all three services (`migrate`, `backend`, `frontend`)
2. Runs `migrate` first, applying Django's schema migrations, then
   fetching and saving Patient/Observation data from the FHIR sandbox
3. Starts `backend` (Django REST API) once `migrate` completes successfully
4. Starts `frontend` (nginx serving the Vue app, proxying `/api/` to `backend`)
Once running, open **http://localhost:5173** in a browser.

## Running Tests

```bash
docker compose run --rm backend python manage.py test patients
```
 
To re-run the migration fresh (clears previously migrated data):
```bash
docker compose down
rm -rf backend/db
docker compose up --build
```
 
## How it works
 
- **`migrate` service**: runs Django's schema setup, then a custom
  management command (`python manage.py run_fhir_migration`) that
  fetches a bounded batch of Patients from FHIR, then fetches
  Observations scoped per already-migrated patient (via FHIR's
  `?subject=` search parameter). Retries on 5xx errors with short
  backoff; does not retry 4xx errors. Runs once, then exits.
- **`backend` service**: Django + Django REST Framework, read-only API
  over the SQLite data populated by `migrate`. Never calls FHIR
  directly.
  - `GET /api/patients` — list migrated patients
  - `GET /api/patients/{fhir_id}` — one patient plus their observations
  - `GET /api/health` — health check
- **`frontend` service**: Vue 3 (via CDN, no build tooling), served by
  nginx. Lists patients, supports search by FHIR ID, shows a hover
  preview of a patient's observations, and a full detail view (alert)
  on click.

  ## Where this differs from Plan.md
 
Plan.md describes the production-scale approach for migrating the full
~50,000-patient dataset (hourly incremental polling via FHIR's history
endpoint, a persisted sync checkpoint, row-level transactions, alerting
on repeated failures). This working slice simplifies deliberately,
given the time scope and the assessment's explicit exclusion of
pagination and real-time sync from Part 2:
 
- `run_fhir_migration` runs once, on demand, fetching a bounded demo
  batch (currently ~60 patients and their observations), not a
  recurring hourly job with a `_since` checkpoint.
- Observations are fetched scoped per already-migrated patient
  (`?subject=Patient/{id}`), rather than generically like Plan.md's
  production design. At full-dataset scale, generic independent
  fetching works because every reference eventually resolves; for this
  bounded slice, independent fetching produced almost no overlap
  between the small Patient and Observation samples, so this was
  changed to guarantee a working, demonstrable end-to-end result.
- The DB schema here is flatter than Plan.md's normalized version
  (e.g. `first_name`/`last_name` directly on `Patient`, no separate
  name/address/language child tables).
- No field-level or disk-level encryption is implemented here. Plan.md's
  Safety section describes this as a production requirement; out of
  scope for this time-boxed slice using synthetic sandbox data only.
- No row-level DB transactions around multi-table inserts, since the
  simplified schema only writes to one table per record.

## What I'd tackle next
 
- Clean up data quality further: several Observations show "Unknown"
  or missing values because they lack a readable code label, use an
  unsupported value shape, or contain genuinely messy/incomplete data
  from the shared public sandbox. I focused more on the infrastructure
  and data-mapping pipeline working correctly end to end, and did a
  first pass at handling the value shapes I actually saw in the sample
  data I pulled; a more thorough review of the full range of Observation
  shapes in the sandbox would let me map more of these correctly rather
  than falling back to raw codes or skipping them.
- Add the checkpoint-based incremental sync described in Plan.md, so
  repeated runs pick up only new/changed data instead of re-fetching
  the same bounded batch each time.
- Add the `total_fetched`/`total_processed` validation summary and
  `JobRun` reporting described in Plan.md (the `JobRun` model exists in
  the schema and is populated on each run, but isn't surfaced anywhere
  in the API or UI yet).
- Encrypt the SQLite file at rest and enforce HTTPS/TLS, per Plan.md's
  Safety section.
- Role-scoped access control (a doctor sees only their own patients),
  once authentication exists (explicitly out of scope for this exercise).

## Test Data
 
Since only a bounded batch of Observations is migrated in this slice,
not every patient will have observations recorded. These FHIR IDs are
confirmed to have observations, useful for testing the hover/click
behavior directly:
 
- `131896579`
- `132080621`

## Where I used AI
 
I've never worked with Django before this exercise, so I used Claude
(Anthropic) heavily to understand the project setup itself: what each
generated file/folder is for, where custom code should live (models,
views, serializers, the management command structure), and how Django's
conventions differ from frameworks I do know.

## Thank You
 
Thanks for putting together this assessment. Between Plan.md and this
working slice, I learned Django and Vue from scratch, this was my
first time building with either, and I came out the other side of this
exercise actually understanding how they fit together, which I
genuinely appreciate.