from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework import status

from patients.models import Patient
from patients.serializers import PatientListSerializer, PatientDetailSerializer


@api_view(["GET"])
def list_patients(request):
    patients = Patient.objects.all().order_by("id")
    serializer = PatientListSerializer(patients, many=True)
    return Response({"patients": serializer.data})


@api_view(["GET"])
def get_patient(request, fhir_id):
    try:
        patient = Patient.objects.get(fhir_id=fhir_id)
    except Patient.DoesNotExist:
        return Response({"detail": "Patient not found"}, status=status.HTTP_404_NOT_FOUND)

    serializer = PatientDetailSerializer(patient)
    return Response(serializer.data)


@api_view(["GET"])
def health(request):
    return Response({"status": "ok"})