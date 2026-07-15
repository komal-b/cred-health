from rest_framework import serializers
from patients.models import Patient, Observation


class PatientListSerializer(serializers.ModelSerializer):
    class Meta:
        model = Patient
        fields = ["id", "fhir_id", "mrn", "first_name", "last_name", "gender", "dob"]


class ObservationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Observation
        fields = ["id", "fhir_id", "code_display", "value", "unit", "effective_date", "status"]


class PatientDetailSerializer(serializers.ModelSerializer):
    observations = ObservationSerializer(many=True, read_only=True)

    class Meta:
        model = Patient
        fields = ["id", "fhir_id", "mrn", "first_name", "last_name", "gender", "dob",
                  "last_updated", "observations"]