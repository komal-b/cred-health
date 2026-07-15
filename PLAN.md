# CREDO HEALTH ASSESSMENT
**Functional Requirements:**
- System will fetch Patient and Observation records from the FHIR and store in DB
- System should display patient data
- When user clicks patient data Observability details should be seen
- System should be able to handle FHIR failures (retry/backoffs)
---
**Non-Functional Requirements:**
- Retrieval of data should be quick, low latency
    - single patient record: 1-10 msec
    - paginated list (100 records/page): <50-100 msec, not full records
- Availability > Consistency — data available even if FHIR update doesn't work, local DB should still be available
---
## API Design

### Record Migration

- GET `https://hapi.fhir.org/baseR4/Patient`
- GET `https://hapi.fhir.org/baseR4/Observation`

### For Our Local Patient System

#### Get all patients (Pagination used)
- **GET** `/patient?limit=100&after_id=200`
- **Response:**
  ```json
  {
    "patients": [
      {
        "name": "",
        "address": "",
        "mrn": ""
        ...
      }
    ]
  }
  ```

#### Get patient observations by ID
- **GET** `/patient/{id}`
- **Response:**
  ```json
  {
    "patient": []
    "observationDetails": []
  }
  ```
---
## DB Design

```
Patient
  id (PK, auto-generated)
  fhir_id (UK)        
  MRN (UK)              
  gender
  dob
  family_name
  last_updated  (From FHIR)      
  created_at

Patient_Name
  id (PK)
  patient_id (FK, Patient.id)
  given_name

Telecom
  id (PK)
  patient_id (FK, Patient.id)
  system  (e.g. 'phone', 'email')
  value
  use  (e.g. 'home', 'mobile')

Address
  id (PK)
  patient_id (FK, Patient.id)
  line
  city
  district
  state
  postal_code

Language
  id (PK)
  code (UK)  (e.g. 'en', 'es')
  display_name  (e.g. 'English')

Patient_Language
  id (PK)
  patient_id (FK, Patient.id)
  language_id (FK, Language.id)
  preferred

Code
  id (PK)
  loinc_code (UK)  (e.g. "2093-3")
  display_name     (Cholesterol [Mass/volume] in Serum or Plasma)

Observation
  id (PK)
  observation_id (UK)    (FHIR id)
  patient_id (Extracting from subject and then getting Patient.id)   
  code_id (FK, Code.id)
  value
  unit
  effective_date
  status
  reference_range_low
  reference_range_high
  performer_name

JobRun
  id (PK)
  started_at
  completed_at
  status
  total_fetched
  total_processed
  error_message (nullable)
```
---

## Overall Appraoch

**Migration mechanism:**

- Migration runs as a polling job on an hourly schedule.
- Each run calls FHIR's history endpoint and fetches only records changed since the last successful sync, rather than pulling the full dataset every time. This assumes a daily API limit of 30 calls.
- Hourly polling uses 24 of those 30 calls, leaving 6 calls in reserve specifically for handling retries, rather than treating all 30 as available for scheduled polling alone.

**Failure handling by status code**

- 4xx errors mean the problem is on our side (most likely a malformed request), so retrying automatically will not help. These are logged with enough detail for a person to diagnose, rather than retried.
- 5xx errors mean the problem is on FHIR's side, so retrying is reasonable.

**Retry logic for 5xx errors**

- Retry up to twice per cycle.
- Wait 10 minutes before the first retry, 20 minutes before the second.
- If both retries fail, stop for that hour and wait for the next scheduled cycle rather than retrying indefinitely.
- Worst case cost per bad hour: 3 calls (1 initial + 2 retries), which fits within the 6-call reserve.
- This budget allows roughly two bad hours per day without running out of reserved calls.

**Escalation beyond a one cycle**

- If failures continue across multiple consecutive cycles (not just within one cycle), that signals a real problem rather than a transient blip.
- At that point, alert a person and pause further automated attempts until someone investigates, instead of retrying quietly forever.

**Observability**

- Every polling run is recorded with: start time, completion time, status, number , and error message if it failed.
- This history is what makes it possible to detect when failures are becoming a pattern rather than a one time failure.

Availability principle (This is for our local system or application)

- System reliability does not depend on FHIR being available at read time.
- If FHIR is down or a polling cycle fails, users reading patient data through our own API are unaffected, since reads come from the local database, not from FHIR directly.
- Data may be slightly stale in that case, but it stays available, this is the deliberate tradeoff of prioritizing availability over strict consistency.

**Pseudocode**

```
FUNCTION run_polling_cycle():
    last_sync_time = get last completed successful run time from JobRun table
    
    IF last_sync_time does not exist:
        result = run_full_backfill()          # first time only, get everything
    ELSE:
        result = fetch_with_retry(last_sync_time)   # normal hourly run, get only changes
    
    IF result is success:
        separate result into patients list and observations list
        
        FOR each patient IN patients list:
            IF patient already exists in DB (check by FHIR patient id):
                update that row
            ELSE:
                insert new row
        
        FOR each observation IN observations list:
            find matching patient's internal id using FHIR patient id from subject
            
            IF matching patient not found:
                skip this observation, log it
                CONTINUE
            
            IF observation already exists in DB (check by FHIR observation id):
                update that row
            ELSE:
                insert new row
        
        save a new row in JobRun table: status = success, records fetched = count, time = now
        reset failed cycle counter to 0
    
    ELSE:
        save a new row in JobRun table: status = failed, error message = result.error, time = now
        increase failed cycle counter by 1
        
        IF failed cycle counter >= 2:
            send alert to a person
            stop automatic polling until someone checks it


FUNCTION fetch_with_retry(since_time):
    attempt = 0
    wait_times = [10 minutes, 20 minutes]
    
    REPEAT:
        response = call FHIR history API with since = since_time
        
        IF response status is 200:
            RETURN success, with response data
        
        IF response status is 400 to 499:
            log error: "our side, needs manual check"
            RETURN failed, no more retries
        
        IF response status is 500 to 599:
            IF attempt is same as number of wait_times already used:
                log error: "FHIR side, retries used up for this cycle"
                RETURN failed
            
            wait for wait_times[attempt]
            attempt = attempt + 1
            REPEAT the loop
```
---
## Data Mapping

## Data Mapping

### Patient

| FHIR field | Internal field |
|---|---|
| `Patient.id` | `patient_id` |
| `identifier[]` (MRN-typed) | `MRN` |
| `name[0].family` | `family_name` |
| `name[0].given[]` | `Patient_Name.given_name` |
| `gender` | `gender` |
| `birthDate` | `dob` |
| `address[]` | `Address` table |
| `telecom[]` | `Telecom` table |
| `communication[]` | `Language` / `Patient_Language` tables |
| `meta.lastUpdated` | `last_updated` |
| *(system-generated)* | `created_at` |

### Observation

| FHIR field | Internal field |
|---|---|
| `Observation.id` | `observation_id` |
| `subject.reference` | `patient_id` (FK) |
| `code.text` / `code.coding[0].display` | `Code` table → `code_id` |
| `valueQuantity.value` | `value` |
| `valueQuantity.unit` | `unit` |
| `effectiveDateTime` | `effective_date` |
| `status` | `status` |
| `referenceRange[0].low.value` | `reference_range_low` |
| `referenceRange[0].high.value` | `reference_range_high` |
| `performer[0].display` | `performer_name` |

---


## Validation

- Compare total records fetched from FHIR against total records processed (inserted, updated, or deliberately skipped with a logged reason) after each run, to confirm nothing was silently lost.
- The sync checkpoint only advances to the current run's time if this comparison matches, meaning the run fully succeeded. If it fails partway, the checkpoint stays at its last successful value, so the next run's query naturally re-covers whatever was missed.
- The first run has no checkpoint yet, so it performs a full backfill using pagination instead of an incremental fetch. The checkpoint is only created once this backfill fully succeeds; if it fails partway, the next attempt repeats the full backfill rather than switching to incremental mode.
- Observations with no mandatory field (subject/patient reference) are not inserted into the DB. Each is written to a log file with its `observation_id` and the reason, so nothing is silently dropped without a trace.
- Observation values are mapped depending on which value field is present, so both common value shapes are captured rather than one being treated as unsupported.
- Track and surface a summary after each run: total fetched, total processed, total skipped with reasons, so data quality is visible rather than assumed.

**Pseudocode:**

```
FUNCTION run_migration_cycle():

    checkpoint = get last successful sync time from JobRun table

    IF checkpoint does not exist:
        result = run_full_backfill()
    ELSE:
        result = fetch_since(checkpoint)

    IF result.total_fetched == result.total_processed:
        save new row in JobRun: status = success, fetched = result.total_fetched, processed = result.total_processed, time = now
        IF checkpoint did not exist before:
            set checkpoint = now   (created for the first time)
        ELSE:
            update checkpoint = now
    ELSE:
        save new row in JobRun: status = failed, fetched = result.total_fetched, processed = result.total_processed, time = now
        do NOT change checkpoint, leave it as it was


FUNCTION run_full_backfill():
    current_page_url = starting Patient search url
    total_fetched = 0
    total_processed = 0

    WHILE current_page_url is not empty:
        response = call FHIR at current_page_url with retry logic

        FOR each record IN response:
            total_fetched = total_fetched + 1
            process_one_record(record)
            total_processed = total_processed + 1   (only if it did not fail)

        IF response has a "next page" link:
            current_page_url = that next page link
        ELSE:
            current_page_url = empty   (this ends the loop)

    RETURN total_fetched, total_processed


FUNCTION fetch_since(checkpoint_time):
    response = call FHIR history endpoint asking for changes since checkpoint_time, with retry logic
    total_fetched = 0
    total_processed = 0

    FOR each record IN response:
        total_fetched = total_fetched + 1
        process_one_record(record)
        total_processed = total_processed + 1   (only if it did not fail)

    RETURN total_fetched, total_processed


FUNCTION process_one_record(record):
    IF record type is Patient:
        IF patient already exists in DB (match by FHIR patient id):
            update that row
        ELSE:
            insert new row

    IF record type is Observation:
        IF record has no subject/patient reference:
            write to skip log file with reason
            STOP here for this record

        find matching patient's internal id using the patient id from subject

        IF no matching patient found:
            write to skip log file with reason
            STOP here for this record

        figure out the value from whichever value field is present

        IF observation already exists in DB (match by FHIR observation id):
            update that row
        ELSE:
            insert new row
```

## Safety (PHI Handling)

- All data in transit (calls to FHIR, calls between our own services) would use HTTPS/TLS encryption.
- Database storage would use encryption at rest at the infrastructure level (e.g. encrypted disk / managed database encryption), covering all patient and observation data, not just identifying fields.
- Engineer access to the database would be limited to a small set of leads via IAM, rather than open to the whole engineering team, and access would be logged/audited so there's a record of who accessed what and when.
- Error and skip logs (from the migration job) would be reviewed to ensure they never contain raw patient data, only ids and error reasons, so debugging logs don't become an unmonitored copy of PHI.

## Rollback

- Each patient's related inserts (Patient row, Address, Patient_Name, etc.) are wrapped in a database transaction, so if any part fails partway (e.g. Patient succeeds but Address fails), the entire record is rolled back automatically, leaving no partially-written data.
- A record that fails and gets rolled back is not counted in total_processed for that run, which naturally causes the fetched-vs-processed validation check to fail and prevents the checkpoint from advancing.
- Since the checkpoint stays at its last successful value, the next scheduled run automatically re-fetches and retries any rolled-back records, no manual recovery step is required.
- If some records in a run succeed and others fail, the successful ones are kept in the database, not rolled back. Only the failed record itself is rolled back (via its own transaction). Keeping the successful ones is safe, since reprocessing them again next run (insert-or-update) causes no harm.
- For the first-time full backfill specifically, since it's a one-time step before the system is live and serving users, a severe partial failure can be handled by clearing the partially-loaded data and restarting the backfill cleanly, rather than needing incremental recovery, since no real usage yet depends on that data.

---
## Note

This plan is written at a high level to describe the overall approach, reasoning, and tradeoffs. The actual implementation in Part 2 is intentionally simpler in scope, given the time constraint, and will differ in some details from what's described here.

All logic, design decisions, and reasoning in this plan are my own, based on my experience and understanding of the problem. I used AI (Claude) to help structure and phrase the writing itself, turning my reasoning into clear sentences and organized sections, not to originate the ideas or decisions.