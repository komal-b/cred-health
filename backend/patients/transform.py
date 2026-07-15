
# Transform FHIR patient resources into a simplified local representation.
def transform_patient(resource):
    fhir_id = resource.get("id")

    names = resource.get("name", [])
    first_name = None
    last_name = None
    if names:
        given = names[0].get("given", [])
        first_name = " ".join(given) if given else None
        last_name = names[0].get("family")

    mrn = None
    for identifier in resource.get("identifier", []):
        system = identifier.get("system", "")
        if "mrn" in system.lower():
            mrn = identifier.get("value")
            break

    return {
        "fhir_id": fhir_id,
        "mrn": mrn,
        "first_name": first_name,
        "last_name": last_name,
        "gender": resource.get("gender"),
        "dob": resource.get("birthDate"),
        "last_updated": resource.get("meta", {}).get("lastUpdated"),
    }


def extract_patient_fhir_id_from_subject(observation_resource):
    subject = observation_resource.get("subject")
    if not subject:
        return None

    reference = subject.get("reference", "")
    if not reference.startswith("Patient/"):
        return None

    return reference.split("Patient/", 1)[1]


def transform_observation(resource):
    fhir_id = resource.get("id")

    code_display = resource.get("code", {}).get("text")
    if not code_display:
        codings = resource.get("code", {}).get("coding", [])
        if codings:
            code_display = codings[0].get("display")

    value = None
    unit = None
    if "valueQuantity" in resource:
        vq = resource["valueQuantity"]
        value = str(vq.get("value")) if vq.get("value") is not None else None
        unit = vq.get("unit")
    elif "valueCodeableConcept" in resource:
        vcc = resource["valueCodeableConcept"]
        value = vcc.get("text")
        if not value:
            codings = vcc.get("coding", [])
            if codings:
                value = codings[0].get("display")
    elif "valueString" in resource:
        value = resource.get("valueString")

    performer_name = None
    performers = resource.get("performer", [])
    if performers:
        performer_name = performers[0].get("display")

    return {
        "fhir_id": fhir_id,
        "patient_fhir_id": extract_patient_fhir_id_from_subject(resource),
        "code_display": code_display,
        "value": value,
        "unit": unit,
        "effective_date": resource.get("effectiveDateTime"),
        "status": resource.get("status"),
        "performer_name": performer_name,
    }