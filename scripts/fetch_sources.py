"""
fetch_sources.py
Legge i feed RSS delle fonti normative, deduplica e salva i nuovi item in data/raw_items.json
"""

import feedparser
import json
import hashlib
import os
from datetime import datetime, timezone
from dateutil import parser as dateparser
from pathlib import Path

# ── Percorsi ──────────────────────────────────────────────────────────────────
BASE_DIR = Path(__file__).parent.parent
DATA_DIR = BASE_DIR / "data"
SEEN_IDS_FILE = DATA_DIR / "seen_ids.json"
RAW_ITEMS_FILE = DATA_DIR / "raw_items.json"

# ── Fonti RSS ─────────────────────────────────────────────────────────────────
SOURCES = [
    {
        "id": "gu_serie_generale",
        "label": "Gazzetta Ufficiale",
        "url": "https://www.gazzettaufficiale.it/rss/SG",
        "paese": "IT",
    },
    {
        "id": "eurlex_oj_l",
        "label": "EUR-Lex — Gazzetta UE (Serie L)",
        "url": "https://eur-lex.europa.eu/EN/display-feed.rss?rssId=222",
        "paese": "EU",
    },
    {
        "id": "eurlex_proposte",
        "label": "EUR-Lex — Proposte Commissione",
        "url": "https://eur-lex.europa.eu/EN/display-feed.rss?rssId=161",
        "paese": "EU",
    },
    {
        "id": "inps_circolari",
        "label": "INPS — Circolari",
        "url": "https://www.inps.it/it/it.rss.circolari.xml",
        "paese": "IT",
    },
    {
        "id": "agenzia_entrate",
        "label": "Agenzia delle Entrate",
        "url": "https://www.agenziaentrate.gov.it/portale/c/portal/rss/entrate?idrss=0753fcb1-1a42-4f8c-f40d-02793c6aefb4",
        "paese": "IT",
    },
    {
        "id": "bancaditalia_vigilanza",
        "label": "Banca d'Italia — Vigilanza",
        "url": "https://www.bancaditalia.it/util/index.rss.html?sezione=/compiti/vigilanza&lingua=it",
        "paese": "IT",
    },
    {
        "id": "senato_ddl",
        "label": "Senato — DDL presentati",
        "url": "https://www.senato.it/static/bgt/UltimiAtti/feedDDL.xml",
        "paese": "IT",
    },
    {
        "id": "gu_ue_recepimento",
        "label": "Gazzetta Ufficiale — Serie UE",
        "url": "https://www.gazzettaufficiale.it/rss/S2",
        "paese": "IT",
    },
]


# ── Helpers ───────────────────────────────────────────────────────────────────

def load_seen_ids() -> set:
    if SEEN_IDS_FILE.exists():
        data = json.loads(SEEN_IDS_FILE.read_text(encoding="utf-8"))
        return set(data.get("seen_ids", []))
    return set()


def save_seen_ids(seen: set) -> None:
    SEEN_IDS_FILE.write_text(
        json.dumps({"seen_ids": list(seen), "last_run": datetime.now(timezone.utc).isoformat()},
                   ensure_ascii=False, indent=2),
        encoding="utf-8"
    )


def load_raw_items() -> list:
    if RAW_ITEMS_FILE.exists():
        return json.loads(RAW_ITEMS_FILE.read_text(encoding="utf-8"))
    return []


def save_raw_items(items: list) -> None:
    RAW_ITEMS_FILE.write_text(
        json.dumps(items, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )


def make_id(entry: dict, source_id: str) -> str:
    raw = f"{source_id}|{entry.get('id') or entry.get('link') or entry.get('title', '')}"
    return hashlib.sha1(raw.encode()).hexdigest()[:16]


def parse_date(entry: dict) -> str:
    """Prova vari campi data e restituisce ISO 8601 o stringa vuota."""
    for field in ("published", "updated", "created"):
        val = entry.get(field)
        if val:
            try:
                return dateparser.parse(val).isoformat()
            except Exception:
                return val
    return datetime.now(timezone.utc).isoformat()


def clean_html(text: str) -> str:
    """Rimuove tag HTML basilari dal summary RSS."""
    import re
    text = re.sub(r"<[^>]+>", " ", text or "")
    text = re.sub(r"\s+", " ", text).strip()
    return text[:1500]  # tronca a 1500 caratteri


# ── Fetch principale ──────────────────────────────────────────────────────────

def fetch_source(source: dict, seen_ids: set) -> list:
    """Fetcha un feed RSS e ritorna i nuovi item non ancora visti."""
    print(f"  → Fetching: {source['label']} ...", end=" ", flush=True)

    try:
        feed = feedparser.parse(source["url"])
    except Exception as e:
        print(f"ERRORE: {e}")
        return []

    if feed.bozo and not feed.entries:
        print(f"feed non valido ({feed.bozo_exception})")
        return []

    new_items = []
    for entry in feed.entries:
        item_id = make_id(entry, source["id"])
        if item_id in seen_ids:
            continue

        item = {
            "id": item_id,
            "source_id": source["id"],
            "fonte": source["label"],
            "paese": source["paese"],
            "titolo_originale": (entry.get("title") or "").strip(),
            "url": entry.get("link") or entry.get("id") or "",
            "pubblicato": parse_date(entry),
            "summary_raw": clean_html(entry.get("summary") or entry.get("description") or ""),
            "fetched_at": datetime.now(timezone.utc).isoformat(),
            "processed": False,
        }
        new_items.append(item)
        seen_ids.add(item_id)

    print(f"{len(new_items)} nuovi item")
    return new_items


def run():
    print("\n=== FETCH SOURCES ===")
    print(f"Timestamp: {datetime.now(timezone.utc).isoformat()}\n")

    DATA_DIR.mkdir(exist_ok=True)
    seen_ids = load_seen_ids()
    existing_items = load_raw_items()

    total_new = 0
    for source in SOURCES:
        new_items = fetch_source(source, seen_ids)
        existing_items.extend(new_items)
        total_new += len(new_items)

    # Mantieni solo ultimi 500 item per non far crescere il file
    existing_items = existing_items[-500:]

    save_raw_items(existing_items)
    save_seen_ids(seen_ids)

    print(f"\nTotale nuovi item: {total_new}")
    print(f"Totale item in archivio: {len(existing_items)}")
    print(f"Salvati in: {RAW_ITEMS_FILE}\n")
    return total_new


if __name__ == "__main__":
    run()
