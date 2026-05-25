#!/usr/bin/env python3
"""
Script di test per il sistema di cache locale degli ETF.
Questo script simula il comportamento del sistema di cache.
"""

import os
import json
from pathlib import Path

# Simula le funzioni di cache
ETF_CACHE_DIR = "etf_data"
Path(ETF_CACHE_DIR).mkdir(exist_ok=True)

def get_etf_cache_path(ticker: str) -> str:
    """Ritorna il percorso del file di cache per un ETF"""
    return os.path.join(ETF_CACHE_DIR, f"{ticker.upper()}.json")

def etf_exists_locally(ticker: str) -> bool:
    """Controlla se un ETF è già presente in cache locale"""
    cache_path = get_etf_cache_path(ticker)
    return os.path.exists(cache_path)

def save_etf_to_cache(ticker: str, data: list):
    """Salva i dati di un ETF nella cache locale"""
    cache_path = get_etf_cache_path(ticker)
    try:
        with open(cache_path, "w") as f:
            json.dump(data, f)
        print(f"✅ ETF {ticker} salvato in cache locale ({len(data)} record)")
    except Exception as e:
        print(f"❌ Errore nel salvataggio di {ticker}: {e}")

def load_etf_from_cache(ticker: str) -> list:
    """Carica i dati di un ETF dalla cache locale"""
    cache_path = get_etf_cache_path(ticker)
    try:
        with open(cache_path, "r") as f:
            data = json.load(f)
            print(f"✅ ETF {ticker} caricato da cache ({len(data)} record)")
            return data
    except Exception as e:
        print(f"❌ Errore nel caricamento di {ticker}: {e}")
        return []

def print_cache_status():
    """Stampa lo stato della cache"""
    print("\n📊 STATO CACHE ETF:")
    print("-" * 50)
    if os.path.exists(ETF_CACHE_DIR):
        files = [f for f in os.listdir(ETF_CACHE_DIR) if f.endswith(".json")]
        if files:
            total_size = 0
            for file in files:
                cache_path = os.path.join(ETF_CACHE_DIR, file)
                size_kb = os.path.getsize(cache_path) / 1024
                total_size += size_kb
                ticker = file.replace(".json", "")
                print(f"  📁 {ticker:<12} - {size_kb:>7.2f} KB")
            print("-" * 50)
            print(f"  📦 Total: {len(files)} ETF in cache")
        else:
            print("  ⚠️  Nessun ETF in cache")
    else:
        print("  ⚠️  Cartella cache non trovata")
    print()

# Test del sistema
if __name__ == "__main__":
    print("\n🧪 TEST SISTEMA CACHE ETF")
    print("=" * 50)
    
    # Test 1: Verifica cache vuota
    print("\n1️⃣  TEST: Cache vuota")
    print_cache_status()
    
    # Test 2: Salva dati mock
    print("\n2️⃣  TEST: Salvataggio ETF in cache")
    mock_etf_data_1 = [
        {"Date": "2026-05-20", "Close": 100.50},
        {"Date": "2026-05-21", "Close": 101.20},
        {"Date": "2026-05-22", "Close": 100.80},
    ]
    mock_etf_data_2 = [
        {"Date": "2026-05-20", "Close": 85.00},
        {"Date": "2026-05-21", "Close": 85.75},
        {"Date": "2026-05-22", "Close": 85.30},
    ]
    
    save_etf_to_cache("SWDA.MI", mock_etf_data_1)
    save_etf_to_cache("EIMI.MI", mock_etf_data_2)
    
    # Test 3: Verifica cache dopo salvataggio
    print("\n3️⃣  TEST: Verifica cache dopo salvataggio")
    print_cache_status()
    
    # Test 4: Carica da cache
    print("4️⃣  TEST: Carica ETF dalla cache")
    if etf_exists_locally("SWDA.MI"):
        data = load_etf_from_cache("SWDA.MI")
    
    # Test 5: ETF non presente in cache
    print("\n5️⃣  TEST: ETF non in cache")
    if not etf_exists_locally("NONEXISTENT.MI"):
        print("✅ ETF NONEXISTENT.MI non trovato in cache (comportamento corretto)")
    
    # Test 6: Mostra il contenuto di un file
    print("\n6️⃣  TEST: Contenuto file cache")
    cache_file = get_etf_cache_path("SWDA.MI")
    with open(cache_file, "r") as f:
        data = json.load(f)
    print(f"  Contenuto di {cache_file}:")
    print(f"  {json.dumps(data, indent=2)[:200]}...")
    
    print("\n" + "=" * 50)
    print("✅ TUTTI I TEST COMPLETATI!")
    print("\nℹ️  Il sistema di cache:")
    print("   - Salva ogni ETF in un file separato")
    print("   - Verifica l'esistenza prima di scaricare")
    print("   - Carica da cache quando disponibile")
    print("   - Organizza i dati in etf_data/")
