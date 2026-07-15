import time
import requests

# Lightweight FHIR client for fetching patient and observation data with retry handling.
FHIR_BASE_URL = "https://hapi.fhir.org/baseR4"

RETRY_WAITS_SECONDS = [2, 5]


def fetch_with_retry(url, params=None):
    attempt = 0

    while True:
        try:
            response = requests.get(url, params=params, timeout=15)
        except requests.exceptions.RequestException as exc:
            if attempt >= len(RETRY_WAITS_SECONDS):
                return False, f"network error after retries: {exc}"
            time.sleep(RETRY_WAITS_SECONDS[attempt])
            attempt += 1
            continue

        if response.status_code == 200:
            return True, response.json()

        if 400 <= response.status_code < 500:
            return False, f"client error {response.status_code}: {response.text[:200]}"

        if response.status_code >= 500:
            if attempt >= len(RETRY_WAITS_SECONDS):
                return False, f"server error {response.status_code} after retries"
            time.sleep(RETRY_WAITS_SECONDS[attempt])
            attempt += 1
            continue

        return False, f"unexpected status {response.status_code}"


def fetch_all_pages(start_url, params=None, max_pages=5):
    all_entries = []
    url = start_url
    current_params = params

    for _ in range(max_pages):
        success, data = fetch_with_retry(url, params=current_params)
        if not success:
            return all_entries, data

        entries = data.get("entry", [])
        all_entries.extend(entries)

        next_link = None
        for link in data.get("link", []):
            if link.get("relation") == "next":
                next_link = link.get("url")
                break

        if not next_link:
            break

        url = next_link
        current_params = None

    return all_entries, None