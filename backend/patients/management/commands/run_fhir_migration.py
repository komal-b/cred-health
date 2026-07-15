import os
from django.core.management.base import BaseCommand
from django.utils import timezone

from patients.models import Patient, Observation, JobRun
from patients.fhir_client import FHIR_BASE_URL, fetch_all_pages, fetch_with_retry
from patients.transform import transform_patient, transform_observation

_db_path = os.environ.get("DB_PATH")
if _db_path:
    SKIP_LOG_PATH = os.path.join(os.path.dirname(_db_path), "skipped_records.log")
else:
    SKIP_LOG_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "..", "skipped_records.log")



def log_skip(reason, record_id):
    with open(SKIP_LOG_PATH, "a") as f:
        f.write(f"{timezone.now().isoformat()} | {record_id} | {reason}\n")


class Command(BaseCommand):
    def handle(self, *args, **options):
        started_at = timezone.now()

        self.stdout.write("Fetching and migrating patients...")
        p_fetched, p_processed, p_error = self.migrate_patients()
        self.stdout.write(
            f"  Patients: fetched={p_fetched}, processed={p_processed}"
            f"{', error=' + p_error if p_error else ''}"
        )

        self.stdout.write("Fetching and migrating observations...")
        o_fetched, o_processed, o_skipped, o_error = self.migrate_observations()
        self.stdout.write(
            f"  Observations: fetched={o_fetched}, processed={o_processed}, "
            f"skipped={o_skipped}{', error=' + o_error if o_error else ''}"
        )

        total_fetched = p_fetched + o_fetched
        total_processed = p_processed + o_processed
        status = "success" if (p_error is None and o_error is None) else "partial_failure"

        JobRun.objects.create(
            started_at=started_at,
            completed_at=timezone.now(),
            status=status,
            total_fetched=total_fetched,
            total_processed=total_processed,
            total_skipped=o_skipped,
            error_message=p_error or o_error,
        )

        self.stdout.write(self.style.SUCCESS(
            f"\nMigration {status}. Fetched={total_fetched}, Processed={total_processed}, Skipped={o_skipped}"
        ))

    def migrate_patients(self, max_pages=3):
        entries, error = fetch_all_pages(f"{FHIR_BASE_URL}/Patient", params={"_count": 20}, max_pages=max_pages)

        total_fetched = 0
        total_processed = 0

        for entry in entries:
            resource = entry.get("resource", {})
            total_fetched += 1
            patient_data = transform_patient(resource)

            if not patient_data["fhir_id"]:
                log_skip("patient has no id", "unknown")
                continue

            Patient.objects.update_or_create(
                fhir_id=patient_data["fhir_id"],
                defaults={
                    "mrn": patient_data["mrn"],
                    "first_name": patient_data["first_name"],
                    "last_name": patient_data["last_name"],
                    "gender": patient_data["gender"],
                    "dob": patient_data["dob"],
                    "last_updated": patient_data["last_updated"],
                },
            )
            total_processed += 1

        return total_fetched, total_processed, error

    def migrate_observations(self, patients_limit=60, observations_per_patient=10):
        total_fetched = 0
        total_processed = 0
        total_skipped = 0
        last_error = None

        patients = Patient.objects.all()[:patients_limit]

        for patient in patients:
            url = f"{FHIR_BASE_URL}/Observation"
            success, data = fetch_with_retry(url, params={
                "subject": f"Patient/{patient.fhir_id}",
                "_count": observations_per_patient,
            })

            if not success:
                last_error = data
                continue

            for entry in data.get("entry", []):
                resource = entry.get("resource", {})
                total_fetched += 1
                obs_data = transform_observation(resource)

                if not obs_data["fhir_id"]:
                    log_skip("observation has no id", "unknown")
                    total_skipped += 1
                    continue

                Observation.objects.update_or_create(
                    fhir_id=obs_data["fhir_id"],
                    defaults={
                        "patient": patient,
                        "code_display": obs_data["code_display"],
                        "value": obs_data["value"],
                        "unit": obs_data["unit"],
                        "effective_date": obs_data["effective_date"],
                        "status": obs_data["status"],
                        "performer_name": obs_data["performer_name"],
                    },
                )
                total_processed += 1

        return total_fetched, total_processed, total_skipped, last_error