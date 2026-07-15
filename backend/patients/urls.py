from django.urls import path
from patients import views

urlpatterns = [
    path("patients", views.list_patients, name="list_patients"),
    path("patients/<str:fhir_id>", views.get_patient, name="get_patient"),
    path("health", views.health, name="health"),
]