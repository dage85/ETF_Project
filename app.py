import yfinance as yf
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel
from typing import List
from contextlib import asynccontextmanager
import uvicorn
import os
import json
import pandas as pd
from pathlib import Path

PORTFOLIOS_FILE = "portfolios.json"
DATA_FILE = "market_data.json"
ETF_CACHE_DIR = "etf_data"

# Assicura che la cartella di cache esista
Path(ETF_CACHE_DIR).mkdir(exist_ok=True)

# --- Modelli Pydantic per il Portafoglio ---
class Asset(BaseModel):
    ticker: str
    weight: float

class Portfolio(BaseModel):
    name: str
    assets: List[Asset]

# --- Stato Globale ---
portfolios_db = {}
market_data = {}

def save_portfolios():
    with open(PORTFOLIOS_FILE, "w") as f:
        json.dump({k: v.dict() for k, v in portfolios_db.items()}, f)

def load_portfolios():
    global portfolios_db
    if os.path.exists(PORTFOLIOS_FILE):
        with open(PORTFOLIOS_FILE, "r") as f:
            data = json.load(f)
            portfolios_db = {k: Portfolio(**v) for k, v in data.items()}

def get_etf_cache_path(ticker: str) -> str:
    """Ritorna il percorso del file di cache per un ETF"""
    return os.path.join(ETF_CACHE_DIR, f"{ticker.upper()}.json")

def etf_exists_locally(ticker: str) -> bool:
    """Controlla se un ETF è già presente in cache locale"""
    cache_path = get_etf_cache_path(ticker)
    return os.path.exists(cache_path)

def load_etf_from_cache(ticker: str) -> dict:
    """Carica i dati di un ETF dalla cache locale"""
    cache_path = get_etf_cache_path(ticker)
    try:
        with open(cache_path, "r") as f:
            return json.load(f)
    except Exception as e:
        print(f"Errore nel caricamento di {ticker} dalla cache: {e}")
        return []

def save_etf_to_cache(ticker: str, data: list):
    """Salva i dati di un ETF nella cache locale"""
    cache_path = get_etf_cache_path(ticker)
    try:
        with open(cache_path, "w") as f:
            json.dump(data, f)
        print(f"ETF {ticker} salvato in cache locale")
    except Exception as e:
        print(f"Errore nel salvataggio di {ticker}: {e}")

def download_and_save_data(tickers: set):
    """Scarica i dati da YF e li salva in locale, verificando prima se già presenti"""
    global market_data
    
    # Carica i dati esistenti se ci sono
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r") as f:
            market_data = json.load(f)
            
    for ticker in tickers:
        ticker_upper = ticker.upper()
        
        # Verifica se è già in cache locale
        if etf_exists_locally(ticker_upper):
            print(f"ETF {ticker_upper} trovato in cache locale. Caricamento...")
            market_data[ticker_upper] = load_etf_from_cache(ticker_upper)
        else:
            print(f"Scaricamento dati per {ticker_upper}...")
            try:
                asset = yf.Ticker(ticker_upper)
                # Scarichiamo 5 anni di default per avere uno storico decente per i portafogli
                hist = asset.history(period="5y") 
                if not hist.empty:
                    hist.reset_index(inplace=True)
                    hist['Date'] = hist['Date'].dt.strftime('%Y-%m-%d')
                    etf_data = hist[['Date', 'Close']].to_dict(orient="records")
                    market_data[ticker_upper] = etf_data
                    # Salva in cache locale
                    save_etf_to_cache(ticker_upper, etf_data)
                else:
                    print(f"ATTENZIONE: Nessun dato trovato per {ticker_upper}")
            except Exception as e:
                print(f"Errore nello scaricamento di {ticker_upper}: {e}")
            
    with open(DATA_FILE, "w") as f:
        json.dump(market_data, f)

@asynccontextmanager
async def lifespan(app: FastAPI):
    # --- ESEGUITO ALLO START ---
    print("Inizializzazione e scarico dati in corso...")
    load_portfolios()
    
    tickers_to_download = set()
    for p in portfolios_db.values():
        for a in p.assets:
            tickers_to_download.add(a.ticker.upper())
            
    if tickers_to_download:
        download_and_save_data(tickers_to_download)
    elif os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r") as f:
            global market_data
            market_data = json.load(f)
            
    print("Avvio completato. Dati pronti.")
    yield
    # --- ESEGUITO ALLO SHUTDOWN (vuoto) ---

app = FastAPI(title="Portfolio ETF API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], 
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
def serve_frontend():
    file_path = os.path.join(os.path.dirname(__file__), "index.html")
    if os.path.exists(file_path):
        return FileResponse(file_path)
    return {"error": "File index.html non trovato nella cartella."}

# --- API Gestione Portafogli ---

@app.post("/api/v1/portfolios")
def create_portfolio(portfolio: Portfolio):
    # Validazione somma dei pesi
    total_weight = sum(a.weight for a in portfolio.assets)
    if abs(total_weight - 100.0) > 0.1: # Margine di tolleranza per float
        raise HTTPException(status_code=400, detail="La somma dei pesi deve essere 100%")
    
    # Assicurati che i ticker siano maiuscoli
    for a in portfolio.assets:
        a.ticker = a.ticker.upper()

    portfolios_db[portfolio.name] = portfolio
    save_portfolios()
    
    # Aggiorna i dati se ci sono nuovi ticker che non abbiamo nel file locale
    existing_tickers = set(market_data.keys())
    new_tickers = set(a.ticker for a in portfolio.assets) - existing_tickers
    if new_tickers:
        download_and_save_data(new_tickers)
        
    return {"message": "Portafoglio creato con successo"}

@app.get("/api/v1/portfolios")
def get_portfolios():
    return list(portfolios_db.keys())

@app.get("/api/v1/etf-cache/status")
def get_etf_cache_status():
    """Ritorna lo stato della cache locale degli ETF"""
    cached_etfs = []
    if os.path.exists(ETF_CACHE_DIR):
        for file in os.listdir(ETF_CACHE_DIR):
            if file.endswith(".json"):
                ticker = file.replace(".json", "")
                cache_path = os.path.join(ETF_CACHE_DIR, file)
                file_size = os.path.getsize(cache_path)
                cached_etfs.append({
                    "ticker": ticker,
                    "cached": True,
                    "file_size_bytes": file_size
                })
    return {"cached_etfs": cached_etfs, "total_cached": len(cached_etfs)}

@app.post("/api/v1/etf-cache/clear/{ticker}")
def clear_etf_cache(ticker: str):
    """Rimuove un ETF dalla cache locale per forzare il download successivo"""
    cache_path = get_etf_cache_path(ticker)
    try:
        if os.path.exists(cache_path):
            os.remove(cache_path)
            # Rimuove anche da market_data
            ticker_upper = ticker.upper()
            if ticker_upper in market_data:
                del market_data[ticker_upper]
            with open(DATA_FILE, "w") as f:
                json.dump(market_data, f)
            return {"message": f"Cache per {ticker} eliminata"}
        else:
            raise HTTPException(status_code=404, detail=f"ETF {ticker} non trovato in cache")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/v1/portfolios/{name}/composition")
def get_portfolio_composition(name: str):
    """Ritorna la composizione del portafoglio (ticker e pesi percentuali)"""
    if name not in portfolios_db:
        raise HTTPException(status_code=404, detail="Portafoglio non trovato")
    
    p = portfolios_db[name]
    assets_detail = [
        {"ticker": asset.ticker, "weight": asset.weight}
        for asset in p.assets
    ]
    
    return {
        "portfolio": name,
        "assets": assets_detail,
        "total_weight": sum(a.weight for a in p.assets)
    }

@app.get("/api/v1/portfolios/{name}/history")
def get_portfolio_history(name: str):
    if name not in portfolios_db:
        raise HTTPException(status_code=404, detail="Portafoglio non trovato")
    
    p = portfolios_db[name]
    dfs = []
    
    # Crea un dataframe per ogni strumento del portafoglio
    for asset in p.assets:
        if asset.ticker not in market_data:
            continue
        df = pd.DataFrame(market_data[asset.ticker])
        df.set_index('Date', inplace=True)
        df.rename(columns={'Close': asset.ticker}, inplace=True)
        dfs.append(df)
        
    if not dfs:
        raise HTTPException(status_code=404, detail="Dati non disponibili per questo portafoglio")
        
    # Allinea i dati unendo i dataframe per Data
    merged = pd.concat(dfs, axis=1)
    merged.ffill(inplace=True) # Gestisce giorni festivi non allineati tra borse diverse
    merged.dropna(inplace=True) # Rimuove le date iniziali in cui mancava qualche ETF
    
    # Calcolo della curva del portafoglio (Base 100)
    portfolio_series = pd.Series(0.0, index=merged.index)
    for asset in p.assets:
        if asset.ticker in merged.columns:
            # Normalizzazione: (Prezzo attuale / Prezzo iniziale) * 100
            normalized_price = (merged[asset.ticker] / merged[asset.ticker].iloc[0]) * 100
            portfolio_series += normalized_price * (asset.weight / 100.0)
            
    result = [{"Date": date, "Value": round(val, 2)} for date, val in portfolio_series.items()]
    return {"portfolio": name, "data": result}

if __name__ == "__main__":
    print("Server in avvio...")
    uvicorn.run(app, host="0.0.0.0", port=8000)