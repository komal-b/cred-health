
from django.test import TestCase
from rest_framework.test import APIClient
from rest_framework import status

from patients.models import Patient, Observation
from patients.transform import transform_patient, transform_observation, extract_patient_fhir_id_from_subject


class TransformPatientTests(TestCase):

    def test_transform_patient_maps_core_fields(self):
        raw = {
            "id": "131896579",
            "identifier": [{"system": "http://hospital.example.org/mrn", "value": "CHC-123456"}],
            "name": [{"use": "official", "family": "Ramirez", "given": ["Carlos"]}],
            "gender": "male",
            "birthDate": "1974-05-12",
        }
        result = transform_patient(raw)

        self.assertEqual(result["fhir_id"], "131896579")
        self.assertEqual(result["mrn"], "CHC-123456")
        self.assertEqual(result["first_name"], "Carlos")
        self.assertEqual(result["last_name"], "Ramirez")
        self.assertEqual(result["gender"], "male")

    def test_transform_patient_handles_missing_optional_fields(self):
        raw = {
            "id": "132080216",
            "name": [{"family": "TestFamily", "given": ["TestGiven"]}],
            "gender": "male",
        }
        result = transform_patient(raw)

        self.assertEqual(result["fhir_id"], "132080216")
        self.assertIsNone(result["mrn"])
        self.assertIsNone(result["dob"])


class TransformObservationTests(TestCase):

    def test_observation_with_no_subject_does_not_crash(self):
        raw = {"id": "131265394", "status": "registered"}

        self.assertIsNone(extract_patient_fhir_id_from_subject(raw))

        result = transform_observation(raw)
        self.assertIsNone(result["patient_fhir_id"])

    def test_transform_observation_handles_value_quantity(self):
        raw = {
            "id": "105794581",
            "status": "final",
            "code": {"text": "Colesterol total"},
            "subject": {"reference": "Patient/testmartin"},
            "valueQuantity": {"value": 182, "unit": "mg/dL"},
        }
        result = transform_observation(raw)

        self.assertEqual(result["patient_fhir_id"], "testmartin")
        self.assertEqual(result["code_display"], "Colesterol total")
        self.assertEqual(result["value"], "182")
        self.assertEqual(result["unit"], "mg/dL")


class PatientAPITests(TestCase):

    def setUp(self):
        self.client = APIClient()
        self.patient = Patient.objects.create(
            fhir_id="p1", mrn="MRN-1", first_name="Maria", last_name="Williams",
            gender="female", dob="1972-06-15",
        )
        Observation.objects.create(
            fhir_id="o1", patient=self.patient, code_display="Body weight",
            value="68", unit="kg", effective_date="2026-02-01", status="final",
        )

    def test_list_patients_returns_migrated_patient(self):
        response = self.client.get("/api/patients")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data["patients"]), 1)
        self.assertEqual(response.data["patients"][0]["first_name"], "Maria")

    def test_get_patient_includes_observations(self):
        response = self.client.get(f"/api/patients/{self.patient.fhir_id}")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["last_name"], "Williams")
        self.assertEqual(len(response.data["observations"]), 1)
        self.assertEqual(response.data["observations"][0]["code_display"], "Body weight")

    def test_get_patient_404_when_not_found(self):
        response = self.client.get("/api/patients/does-not-exist")
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)