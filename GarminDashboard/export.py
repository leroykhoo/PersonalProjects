import json
from datetime import date, timedelta
import os
import csv
import sqlite3
from garminconnect import Garmin
from pathlib import Path

OUTPUT_DIR = Path(r"C:\Users\Leroy\Documents\GitHub\PersonalProjects\GarminDashboard")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# 1. Anmeldedaten (Credentials)
EMAIL = os.getenv("GARMIN_EMAIL")
PASSWORD = os.getenv("GARMIN_PASSWORD")


def first_non_null(*values):
    for value in values:
        if value is not None:
            return value
    return None


def get_nested(data, path):
    current = data
    for key in path:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
        if current is None:
            return None
    return current


def find_key_case_insensitive(data, wanted_key):
    if not isinstance(data, dict):
        return None
    wanted = wanted_key.lower()
    for key, value in data.items():
        if key.lower() == wanted:
            return value
    return None


def find_first_key_containing(data, candidates):
    if not isinstance(data, dict):
        return None
    lowered_candidates = [candidate.lower() for candidate in candidates]
    for key, value in data.items():
        key_lower = key.lower()
        if any(candidate in key_lower for candidate in lowered_candidates):
            return value
    return None


def get_first_value_from_map(data):
    if not isinstance(data, dict) or not data:
        return None
    for value in data.values():
        return value
    return None


def extract_load_focus(training_status):
    dto = get_nested(
        training_status,
        ["mostRecentTrainingLoadBalance", "metricsTrainingLoadBalanceDTOMap"],
    )
    first_device = get_first_value_from_map(dto)
    return first_non_null(
        get_nested(first_device, ["trainingBalanceFeedbackPhrase"]),
        find_key_case_insensitive(training_status, "loadFocus"),
        find_key_case_insensitive(training_status, "trainingLoadBalance"),
        find_first_key_containing(training_status, ["loadfocus", "load_balance"]),
    )


def extract_acute_training_load(training_status):
    latest_status_map = get_nested(
        training_status,
        ["mostRecentTrainingStatus", "latestTrainingStatusData"],
    )
    first_device = get_first_value_from_map(latest_status_map)
    acute_dto = get_nested(first_device, ["acuteTrainingLoadDTO"]) or {}
    if isinstance(acute_dto, dict) and acute_dto:
        return acute_dto
    return {}


def extract_vo2max(max_metrics, training_status):
    return first_non_null(
        max_metrics.get("vo2Max"),
        find_key_case_insensitive(max_metrics, "vo2MaxRunning"),
        get_nested(training_status, ["mostRecentVO2Max", "generic", "vo2MaxValue"]),
        get_nested(training_status, ["mostRecentVO2Max", "generic", "vo2MaxPreciseValue"]),
        find_first_key_containing(max_metrics, ["vo2"]),
    )


def append_flat_exports(metrics):
    acute = metrics.get("acute_load") if isinstance(metrics.get("acute_load"), dict) else {}
    training_status = metrics.get("training_status") if isinstance(metrics.get("training_status"), dict) else {}
    latest_status_map = get_nested(training_status, ["mostRecentTrainingStatus", "latestTrainingStatusData"]) or {}
    first_latest_status = get_first_value_from_map(latest_status_map) or {}

    row = {
        "date": metrics.get("date"),
        "resting_hr": get_nested(metrics, ["heart_rate", "resting"]),
        "min_hr": get_nested(metrics, ["heart_rate", "min"]),
        "max_hr": get_nested(metrics, ["heart_rate", "max"]),
        "sleep_score": metrics.get("sleep_score"),
        "load_focus": metrics.get("load_focus"),
        "acute_load": acute.get("dailyTrainingLoadAcute"),
        "acute_chronic_ratio": acute.get("dailyAcuteChronicWorkloadRatio"),
        "acute_status": acute.get("acwrStatus"),
        "calories": metrics.get("calories"),
        "steps": metrics.get("steps"),
        "vo2max": metrics.get("vo2max"),
        "training_status_phrase": first_latest_status.get("trainingStatusFeedbackPhrase"),
    }

    # CSV export for Excel / Power BI import.
    csv_path = OUTPUT_DIR / "dashboard_metrics_history.csv"
    csv_exists = csv_path.exists()
    with open(csv_path, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(row.keys()))
        if not csv_exists:
            writer.writeheader()
        writer.writerow(row)

    # SQLite export for BI tools and lightweight querying.
    db_path = OUTPUT_DIR / "garmin_dashboard.db"
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS metrics_history (
                date TEXT PRIMARY KEY,
                resting_hr REAL,
                min_hr REAL,
                max_hr REAL,
                sleep_score REAL,
                load_focus TEXT,
                acute_load REAL,
                acute_chronic_ratio REAL,
                acute_status TEXT,
                calories REAL,
                steps REAL,
                vo2max REAL,
                training_status_phrase TEXT
            )
            """
        )
        conn.execute(
            """
            INSERT INTO metrics_history (
                date, resting_hr, min_hr, max_hr, sleep_score, load_focus,
                acute_load, acute_chronic_ratio, acute_status, calories,
                steps, vo2max, training_status_phrase
            )
            VALUES (
                :date, :resting_hr, :min_hr, :max_hr, :sleep_score, :load_focus,
                :acute_load, :acute_chronic_ratio, :acute_status, :calories,
                :steps, :vo2max, :training_status_phrase
            )
            ON CONFLICT(date) DO UPDATE SET
                resting_hr = excluded.resting_hr,
                min_hr = excluded.min_hr,
                max_hr = excluded.max_hr,
                sleep_score = excluded.sleep_score,
                load_focus = excluded.load_focus,
                acute_load = excluded.acute_load,
                acute_chronic_ratio = excluded.acute_chronic_ratio,
                acute_status = excluded.acute_status,
                calories = excluded.calories,
                steps = excluded.steps,
                vo2max = excluded.vo2max,
                training_status_phrase = excluded.training_status_phrase
            """,
            row,
        )


def save_json(filename, data):
    with open(OUTPUT_DIR / filename, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4)

def main():
    try:
        # 2. Authentifizierung (Authentication)
        # ueberpruefe nur die E-Mail, drucke niemals das Passwort!
        print(f"Verbinde mit Garmin Connect fuer Email: {EMAIL} ...")
        client = Garmin(EMAIL, PASSWORD)
        client.login()
        print("Erfolgreich eingeloggt!")

        # 3. Aktivitäten abrufen (Fetch Activities)
        print("Lade Aktivitäten herunter...")
        activities = client.get_activities(0, 5)
        save_json("aktivitaeten.json", activities)
        print("Aktivitäten gespeichert (aktivitaeten.json).")

        # 4. Tagesdaten abrufen (Daily metrics)
        yesterday = (date.today() - timedelta(days=1)).isoformat()
        print(f"Lade Gesundheitsdaten fuer gestern ({yesterday}) herunter...")

        hr_data = client.get_heart_rates(yesterday) or {}
        sleep_data = client.get_sleep_data(yesterday) or {}
        training_status = client.get_training_status(yesterday) or {}
        training_readiness = client.get_morning_training_readiness(yesterday) or {}
        user_summary = client.get_user_summary(yesterday) or {}
        max_metrics = client.get_max_metrics(yesterday) or {}

        # Raw Responses fuer Debugging speichern.
        print("Speichere Rohdaten in JSON-Dateien...")
        save_json("herzfrequenz.json", hr_data)
        save_json("sleep_data.json", sleep_data)
        save_json("training_status.json", training_status)
        save_json("training_readiness.json", training_readiness)
        save_json("user_summary.json", user_summary)
        save_json("max_metrics.json", max_metrics)

        sleep_score = first_non_null(
            get_nested(sleep_data, ["dailySleepDTO", "sleepScores", "overall", "value"]),
            get_nested(sleep_data, ["dailySleepDTO", "sleepScores", "overall", "score"]),
            find_key_case_insensitive(training_readiness, "sleepScore"),
        )

        load_focus = extract_load_focus(training_status)
        acute_load = extract_acute_training_load(training_status)

        metrics = {
            "date": yesterday,
            "heart_rate": {
                "resting": first_non_null(hr_data.get("restingHeartRate"), user_summary.get("restingHeartRate")),
                "min": hr_data.get("minHeartRate"),
                "max": hr_data.get("maxHeartRate"),
            },
            "sleep_score": sleep_score,
            "load_focus": load_focus,
            "acute_load": acute_load,
            "calories": first_non_null(
                user_summary.get("totalKilocalories"),
                user_summary.get("activeKilocalories"),
            ),
            "steps": user_summary.get("totalSteps"),
            "vo2max": extract_vo2max(max_metrics, training_status),
            "training_status": training_status,
        }

        save_json("dashboard_metrics.json", metrics)
        append_flat_exports(metrics)
        print("Metriken gespeichert (dashboard_metrics.json).")

    except Exception as e:
        print(f"Ein Fehler ist aufgetreten (Exception occurred): {e}")

if __name__ == "__main__":
    main()