# Normativa per Tutti

Le nuove leggi e gli atti normativi italiani ed europei, **spiegati in linguaggio semplice** e aggiornati automaticamente ogni giorno.

Servizio informativo non ufficiale: i riassunti sono generati da AI a partire da fonti ufficiali e possono contenere imprecisioni. Verificare sempre il testo ufficiale. Non costituisce consulenza legale o fiscale.

## Come funziona

Pipeline in 3 fasi, completamente automatica:

1. **Fetch** — [`scripts/fetch_sources.py`](scripts/fetch_sources.py) legge i feed RSS delle fonti ufficiali (Gazzetta Ufficiale, EUR-Lex, INPS, Agenzia delle Entrate, Banca d'Italia, Senato), deduplica e salva i nuovi atti in `data/raw_items.json`.
2. **Elaborazione AI** — [`scripts/process_with_ai.py`](scripts/process_with_ai.py) chiede a un modello LLM (via [OpenRouter](https://openrouter.ai), modelli gratuiti con fallback automatico) di riscrivere ogni atto in italiano semplice e strutturato, e salva il risultato in `data/notizie.json`.
3. **Dashboard** — [`index.html`](index.html) è una pagina statica che legge `data/notizie.json` e mostra le notizie in schede filtrabili per paese, importanza e categoria, con ricerca testuale e dettaglio espandibile per ogni notizia.

L'aggiornamento giornaliero è gestito da GitHub Actions ([`.github/workflows/update.yml`](.github/workflows/update.yml)), che esegue fetch + AI e committa i dati aggiornati.

## Per ogni notizia

- **Titolo popolare** e categoria
- **Cosa cambia** (punti chiave)
- **Chi interessa**
- **Riassunto esteso**, **Impatto** e **Cosa devi fare** (sezione "Leggi di più")
- Data di vigenza, fonte e link al testo ufficiale

## Esecuzione locale

```bash
pip install -r requirements.txt
# crea un file .env con la tua chiave OpenRouter:
#   OPENROUTER_API_KEY=sk-or-...
python run_all.py
# poi apri index.html nel browser
```

> Il file `.env` con la chiave **non va mai committato** (è già in `.gitignore`).

## Pubblicazione gratuita (GitHub Pages + Actions)

1. Su GitHub: **Settings → Secrets and variables → Actions → New repository secret**
   - Nome: `OPENROUTER_API_KEY` — Valore: la tua chiave `sk-or-...`
2. **Settings → Pages**: Source = `Deploy from a branch`, Branch = `main`, cartella `/ (root)`.
   Il sito sarà pubblicato all'indirizzo indicato da GitHub (es. `https://<utente>.github.io/<repo>/`).
3. Il workflow gira ogni giorno alle 06:00 UTC. Puoi anche lanciarlo a mano da **Actions → Aggiorna Dashboard Normativa → Run workflow**.

Su repository **pubblici** GitHub Actions e GitHub Pages sono gratuiti. Usando i modelli `:free` di OpenRouter anche l'elaborazione AI è gratuita (con rate limit).

## Fonti

Gazzetta Ufficiale · EUR-Lex · INPS · Agenzia delle Entrate · Banca d'Italia · Senato
