from django.db import models


class Patient(models.Model):
    fhir_id = models.CharField(max_length=64, unique=True)
    mrn = models.CharField(max_length=64, null=True, blank=True)
    first_name = models.CharField(max_length=100, null=True, blank=True)
    last_name = models.CharField(max_length=100, null=True, blank=True)
    gender = models.CharField(max_length=20, null=True, blank=True)
    dob = models.CharField(max_length=20, null=True, blank=True)
    last_updated = models.CharField(max_length=64, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.first_name} {self.last_name} ({self.fhir_id})"


class Observation(models.Model):
    fhir_id = models.CharField(max_length=64, unique=True)
    patient = models.ForeignKey(
        Patient,
        on_delete=models.CASCADE,
        related_name="observations",
        null=True,
        blank=True,
    )
    code_display = models.CharField(max_length=255, null=True, blank=True)
    value = models.CharField(max_length=255, null=True, blank=True)
    unit = models.CharField(max_length=50, null=True, blank=True)
    effective_date = models.CharField(max_length=64, null=True, blank=True)
    status = models.CharField(max_length=30, null=True, blank=True)
    performer_name = models.CharField(max_length=100, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)


class JobRun(models.Model):
    started_at = models.DateTimeField()
    completed_at = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=20)
    total_fetched = models.IntegerField(default=0)
    total_processed = models.IntegerField(default=0)
    total_skipped = models.IntegerField(default=0)
    error_message = models.TextField(null=True, blank=True)