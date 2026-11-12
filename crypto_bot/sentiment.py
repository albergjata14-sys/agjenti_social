"""Indeksi "Frika dhe lakmia" (Crypto Fear & Greed Index) nga alternative.me: falas, pa çelës.

Kushti i përdorimit: burimi duhet përmendur pranë të dhënës (paneli e bën këtë).
"""
import requests

URL = "https://api.alternative.me/fng/"
LABELS = {"Extreme Fear": "Frikë e madhe", "Fear": "Frikë", "Neutral": "Neutral", "Greed": "Lakmi",
          "Extreme Greed": "Lakmi e madhe"}


def fear_greed() -> dict:
    """Vlera e sotme (0–100), emërtimi dhe vlera e djeshme."""
    r = requests.get(URL, params={"limit": 2}, timeout=10)
    r.raise_for_status()
    data = r.json()["data"]
    now = data[0]
    return {"value": int(now["value"]), "label": LABELS.get(now["value_classification"], now["value_classification"]),
            "yesterday": int(data[1]["value"]) if len(data) > 1 else None}
