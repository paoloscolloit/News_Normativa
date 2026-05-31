"""
run_all.py  —  Esecuzione locale completa del pipeline
Uso:  python run_all.py

Richiede la variabile d'ambiente OPENROUTER_API_KEY impostata.
  macOS/Linux:  export OPENROUTER_API_KEY="sk-or-..."
  Windows CMD:  set OPENROUTER_API_KEY=sk-or-...
  Windows PS:   $env:OPENROUTER_API_KEY="sk-or-..."
"""

import sys
import os

# Aggiunge scripts/ al path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "scripts"))

from fetch_sources import run as fetch_run
from process_with_ai import run as process_run


def main():
    print("=" * 50)
    print("  NORMATIVA PER TUTTI — Pipeline completo")
    print("=" * 50)

    # Step 1: Fetch
    fetch_run()

    # Step 2: Elaborazione AI — gira sempre, processa tutti gli item non ancora elaborati
    process_run()

    print("\n" + "=" * 50)
    print("  Pipeline completato!")
    print("  Apri index.html nel browser per vedere i risultati.")
    print("=" * 50)


if __name__ == "__main__":
    main()
