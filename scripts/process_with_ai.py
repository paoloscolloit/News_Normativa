"""
process_with_ai.py
Chiama Gemini Flash (via OpenRouter) per riassumere ogni atto normativo grezzo
in linguaggio semplice, poi salva i risultati in data/notizie.json
"""

import json
import os
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path
from openai import OpenAI

# Carica .env se presente (senza dipendenze esterne)
_env_file = Path(__file__).parent.parent / ".env"
if _env_file.exists():
    for _line in _env_file.read_text(encoding="utf-8").splitlines():
        _line = _line.strip()
        if _line and not _line.startswith("#") and "=" in _line:
            _k, _v = _line.split("=", 1)
            os.environ.setdefault(_k.strip(), _v.strip())

# ── Percorsi ──────────────────────────────────────────────────────────────────
BASE_DIR = Path(__file__).parent.parent
DATA_DIR = BASE_DIR / "data"
RAW_ITEMS_FILE = DATA_DIR / "raw_items.json"
NOTIZIE_FILE = DATA_DIR / "notizie.json"

# ── Configurazione OpenRouter ─────────────────────────────────────────────────
OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY", "")
# Modelli free da tentare in ordine — usa il primo che risponde
# Ordinati per qualità su testi legali italiani e affidabilità JSON output
MODELS_FALLBACK = [
    "nousresearch/hermes-3-llama-3.1-405b:free",  # 405B — miglior qualità disponibile
    "openai/gpt-oss-120b:free",                    # 120B — ottimo per JSON strutturato
    "nvidia/nemotron-3-super-120b-a12b:free",      # 120B — buon italiano
    "meta-llama/llama-3.3-70b-instruct:free",      # 70B — affidabile, buon italiano
    "deepseek/deepseek-v4-flash:free",             # veloce, buona qualità
    "qwen/qwen3-next-80b-a3b-instruct:free",       # 80B — forte su multilingua
    "google/gemma-4-31b-it:free",                  # 31B — ottimizzato per instruction following
]
MODEL = None  # viene risolto automaticamente al primo avvio

MAX_ITEMS_PER_RUN = 30                        # limite per run (rispetta rate limit free)
RETRY_ATTEMPTS = 2
RETRY_DELAY = 3  # secondi tra retry

CATEGORIE = [
    "Fisco e Tributi",
    "Lavoro e Previdenza",
    "Imprese e Mercato",
    "Banche e Finanza",
    "Ambiente e Energia",
    "Salute e Farmaci",
    "Digitale e Privacy",
    "Appalti Pubblici",
    "Giustizia e Diritti",
    "Iter Legislativo",
    "Trasporti",
    "Agricoltura e Alimentare",
    "Istruzione e Ricerca",
    "Altro",
]

PROMPT_TEMPLATE = """Sei un esperto di normativa italiana ed europea che scrive per cittadini comuni, non per avvocati.

Leggi questo atto normativo e spiegalo in modo semplice, completo e diretto.
Rispondi SOLO con un oggetto JSON valido. Niente markdown, niente testo prima o dopo il JSON.

Struttura JSON richiesta (rispetta esattamente questi campi):
{{
  "titolo_popolare": "titolo breve e chiaro, max 12 parole, zero gergo legale",
  "riassunto_esteso": "spiegazione discorsiva di 4-7 frasi che racconta cosa stabilisce l'atto e perché è stato adottato, in linguaggio semplice e scorrevole. Niente elenchi qui, testo continuo.",
  "cosa_cambia": [
    "prima cosa concreta che cambia per le persone (frase semplice, max 25 parole)",
    "seconda cosa che cambia (se esiste)",
    "terza cosa (se rilevante)",
    "quarta cosa (solo se davvero rilevante)"
  ],
  "chi_interessa": "a chi si applica, es: tutti i lavoratori dipendenti / le piccole imprese / i proprietari di auto / tutti",
  "cosa_devi_fare": "azioni pratiche o adempimenti per chi è interessato (es: presentare domanda entro X, aggiornare i contratti, nessuna azione richiesta). Frase breve.",
  "impatto": "qual e' l'effetto concreto e perche' conta, in 1-2 frasi (es: bollette piu' basse, piu' tutele sul lavoro, nuovi obblighi per le imprese)",
  "data_vigenza": "es: dal 1 gennaio 2026 / in vigore da subito / da definire con decreto attuativo",
  "categoria": "{categorie}",
  "importanza": 1, 2 oppure 3  (1=marginale, 2=rilevante per chi interessa, 3=impatto su molte persone)
}}

Regole: scrivi sempre in italiano. Se un'informazione non e' deducibile dal testo, usa una stima ragionevole o "non specificato". Non inventare numeri, importi o date precise se non presenti.

ATTO DA ANALIZZARE:
Fonte: {fonte} ({paese})
Titolo originale: {titolo}
Testo/Sommario: {testo}
"""


# ── Client OpenRouter ─────────────────────────────────────────────────────────

def get_client() -> OpenAI:
    if not OPENROUTER_API_KEY:
        raise ValueError(
            "Variabile d'ambiente OPENROUTER_API_KEY non impostata.\n"
            "Metti OPENROUTER_API_KEY=sk-or-... nel file .env"
        )
    return OpenAI(
        base_url="https://openrouter.ai/api/v1",
        api_key=OPENROUTER_API_KEY,
    )


def resolve_model(client: OpenAI) -> str:
    """Trova il primo modello free disponibile e non rate-limitato."""
    print("  Ricerca modello disponibile...")
    for model_id in MODELS_FALLBACK:
        print(f"    Provo {model_id}...", end=" ", flush=True)
        try:
            client.chat.completions.create(
                model=model_id,
                messages=[{"role": "user", "content": "ok"}],
                max_tokens=1,
            )
            print("✓ disponibile")
            return model_id
        except Exception as e:
            err = str(e)
            if "404" in err or "No endpoints" in err:
                print("✗ non disponibile")
                continue
            if "429" in err or "rate" in err.lower():
                print("✗ rate limited, provo il prossimo")
                continue
            # Altro errore (es. auth) — interrompi
            raise
    raise RuntimeError(
        "Nessun modello free disponibile al momento. Riprova tra qualche minuto."
    )


# ── Helpers ───────────────────────────────────────────────────────────────────

def load_json(path: Path, default):
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8-sig"))
    return default


def save_json(path: Path, data) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def build_prompt(item: dict) -> str:
    testo = item.get("summary_raw") or item.get("titolo_originale", "")
    return PROMPT_TEMPLATE.format(
        categorie=" | ".join(CATEGORIE),
        fonte=item.get("fonte", ""),
        paese=item.get("paese", ""),
        titolo=item.get("titolo_originale", ""),
        testo=testo[:2000],
    )


def parse_ai_response(text: str) -> dict | None:
    """Estrae il JSON dalla risposta del modello (gestisce markdown fence se presenti)."""
    text = text.strip()
    # rimuovi eventuali ```json ... ```
    if text.startswith("```"):
        lines = text.split("\n")
        text = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        # Tenta estrazione bruta del primo { ... }
        import re
        m = re.search(r"\{.*\}", text, re.DOTALL)
        if m:
            try:
                return json.loads(m.group())
            except Exception:
                pass
    return None


def call_ai(client: OpenAI, item: dict, model: str) -> dict | None:
    prompt = build_prompt(item)

    for attempt in range(1, RETRY_ATTEMPTS + 1):
        try:
            response = client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=1200,
                temperature=0.2,
            )
            raw_text = response.choices[0].message.content or ""
            result = parse_ai_response(raw_text)
            if result:
                return result
            print(f"    ⚠ JSON non valido (tentativo {attempt})")
        except Exception as e:
            err = str(e)
            # Legge retry_after dal messaggio di errore se presente
            wait = RETRY_DELAY * attempt
            try:
                import re, json as _json
                m = re.search(r"retry_after_seconds['\"]:\s*([\d.]+)", err)
                if m:
                    wait = int(float(m.group(1))) + 2
            except Exception:
                pass
            if "429" in err or "rate" in err.lower():
                print(f"    ⚠ Rate limit (tentativo {attempt}) — aspetto {wait}s...")
            else:
                print(f"    ⚠ Errore API (tentativo {attempt}): {err[:120]}")
            if attempt < RETRY_ATTEMPTS:
                time.sleep(wait)

    return None


def validate_and_enrich(ai_result: dict, item: dict) -> dict:
    """Normalizza e arricchisce il risultato AI con i metadati dell'item."""
    # Assicura che cosa_cambia sia una lista
    cosa_cambia = ai_result.get("cosa_cambia", [])
    if isinstance(cosa_cambia, str):
        cosa_cambia = [cosa_cambia]

    # Clamp importanza tra 1 e 3
    importanza = ai_result.get("importanza", 2)
    try:
        importanza = max(1, min(3, int(importanza)))
    except Exception:
        importanza = 2

    # Valida categoria
    categoria = ai_result.get("categoria", "Altro")
    if categoria not in CATEGORIE:
        categoria = "Altro"

    return {
        "id": item["id"],
        "titolo_popolare": (ai_result.get("titolo_popolare") or item["titolo_originale"])[:120],
        "titolo_originale": item["titolo_originale"],
        "riassunto_esteso": (ai_result.get("riassunto_esteso") or "").strip(),
        "cosa_cambia": [c for c in cosa_cambia if c][:4],
        "chi_interessa": ai_result.get("chi_interessa", ""),
        "cosa_devi_fare": (ai_result.get("cosa_devi_fare") or "").strip(),
        "impatto": (ai_result.get("impatto") or "").strip(),
        "data_vigenza": ai_result.get("data_vigenza", ""),
        "categoria": categoria,
        "importanza": importanza,
        "fonte": item["fonte"],
        "paese": item["paese"],
        "url": item["url"],
        "pubblicato": item["pubblicato"],
        "processed_at": datetime.now(timezone.utc).isoformat(),
    }


# ── Pulizia item vecchi ───────────────────────────────────────────────────────

def remove_old_items(items: list, days: int = 60) -> list:
    """Rimuove item più vecchi di N giorni per contenere la dimensione del file."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    fresh = []
    for item in items:
        try:
            pub = datetime.fromisoformat(item["pubblicato"].replace("Z", "+00:00"))
            if pub >= cutoff:
                fresh.append(item)
        except Exception:
            fresh.append(item)  # tieni se non riesce a parsare la data
    return fresh


# ── Main ──────────────────────────────────────────────────────────────────────

def run():
    print("\n=== PROCESS WITH AI ===")
    print(f"Timestamp: {datetime.now(timezone.utc).isoformat()}\n")

    raw_items = load_json(RAW_ITEMS_FILE, [])
    notizie_data = load_json(NOTIZIE_FILE, {"last_updated": None, "items": []})
    existing_notizie = notizie_data.get("items", [])

    # ID già processati (escludi le demo)
    processed_ids = {n["id"] for n in existing_notizie if not n["id"].startswith("demo")}

    # Item da processare (non ancora elaborati)
    to_process = [
        item for item in raw_items
        if not item.get("processed") and item["id"] not in processed_ids
    ]

    if not to_process:
        print("Nessun nuovo item da processare.")
        return 0

    # Limita a MAX_ITEMS_PER_RUN
    to_process = to_process[:MAX_ITEMS_PER_RUN]
    print(f"Item da processare: {len(to_process)}\n")

    client = get_client()
    # Trova automaticamente il primo modello free disponibile
    active_model = resolve_model(client)
    print(f"Modello attivo: {active_model}\n")

    new_notizie = []
    failed = 0

    for i, item in enumerate(to_process, 1):
        print(f"[{i}/{len(to_process)}] {item['titolo_originale'][:70]}...")
        ai_result = call_ai(client, item, active_model)

        if ai_result:
            notizia = validate_and_enrich(ai_result, item)
            new_notizie.append(notizia)
            item["processed"] = True
            print(f"    ✓ [{notizia['categoria']}] {notizia['titolo_popolare'][:60]}")
        else:
            failed += 1
            item["processed"] = False
            print(f"    ✗ Saltato (risposta AI non valida)")

        # Pausa tra richieste per rispettare rate limit del tier free
        if i < len(to_process):
            time.sleep(1.5)

    # Aggiorna raw_items con flag processed
    save_json(RAW_ITEMS_FILE, raw_items)

    # Aggiunge nuove notizie e rimuove quelle vecchie
    all_notizie = existing_notizie + new_notizie
    all_notizie = remove_old_items(all_notizie, days=60)
    # Ordina per data pubblicazione (più recenti prima)
    all_notizie.sort(key=lambda x: x.get("pubblicato", ""), reverse=True)

    notizie_data = {
        "last_updated": datetime.now(timezone.utc).isoformat(),
        "total": len(all_notizie),
        "items": all_notizie,
    }
    save_json(NOTIZIE_FILE, notizie_data)

    print(f"\n✓ Nuove notizie aggiunte: {len(new_notizie)}")
    print(f"✗ Item falliti: {failed}")
    print(f"Totale in archivio: {len(all_notizie)}")
    print(f"Salvato in: {NOTIZIE_FILE}\n")
    return len(new_notizie)


if __name__ == "__main__":
    run()
