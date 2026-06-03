import yfinance as yf
from fastapi import FastAPI, HTTPException, Header
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
from typing import List, Dict

# Cartelle separate per dati globali e dati di sessione
SESSION_DIR = "portfolios_sessions"
DATA_FILE = "market_data.json"
ETF_CACHE_DIR = "etf_data"

# Assicura che le cartelle esistano
Path(ETF_CACHE_DIR).mkdir(exist_ok=True)
Path(SESSION_DIR).mkdir(exist_ok=True)

# --- Modelli Pydantic ---
class Asset(BaseModel):
    ticker: str
    weight: float

class Portfolio(BaseModel):
    name: str
    assets: List[Asset]

# --- Stato Globale (solo per la cache di mercato) ---
market_data = {}

# --- Funzioni Helper per la Sessione ---
def get_session_file(session_id: str) -> str:
    """Ritorna il percorso del file di portafogli associato alla sessione, ripulendo l'id"""
    safe_id = "".join(c for c in session_id if c.isalnum() or c in "-_")
    return os.path.join(SESSION_DIR, f"portfolios_{safe_id}.json")

def load_session_portfolios(session_id: str) -> dict:
    """Carica i portafogli esclusivi della sessione corrente"""
    file_path = get_session_file(session_id)
    if os.path.exists(file_path):
        with open(file_path, "r") as f:
            data = json.load(f)
            return {k: Portfolio(**v) for k, v in data.items()}
    return {}

def save_session_portfolios(session_id: str, portfolios: dict):
    """Salva i portafogli esclusivi della sessione corrente"""
    file_path = get_session_file(session_id)
    with open(file_path, "w") as f:
        json.dump({k: v.dict() for k, v in portfolios.items()}, f)

# --- Funzioni di Cache ETF (Invariate e Globali) ---
def get_etf_cache_path(ticker: str) -> str:
    return os.path.join(ETF_CACHE_DIR, f"{ticker.upper()}.json")

def etf_exists_locally(ticker: str) -> bool:
    return os.path.exists(get_etf_cache_path(ticker))

def load_etf_from_cache(ticker: str) -> dict:
    try:
        with open(get_etf_cache_path(ticker), "r") as f:
            return json.load(f)
    except Exception as e:
        print(f"Errore cache: {e}")
        return []

def save_etf_to_cache(ticker: str, data: list):
    try:
        with open(get_etf_cache_path(ticker), "w") as f:
            json.dump(data, f)
    except Exception as e:
        print(f"Errore salvataggio cache: {e}")

def download_and_save_data(tickers: set):
    global market_data
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r") as f:
            market_data = json.load(f)
            
    for ticker in tickers:
        ticker_upper = ticker.upper()
        if etf_exists_locally(ticker_upper):
            market_data[ticker_upper] = load_etf_from_cache(ticker_upper)
        else:
            try:
                asset = yf.Ticker(ticker_upper)
                hist = asset.history(period="5y") 
                if not hist.empty:
                    hist.reset_index(inplace=True)
                    hist['Date'] = hist['Date'].dt.strftime('%Y-%m-%d')
                    etf_data = hist[['Date', 'Close']].to_dict(orient="records")
                    market_data[ticker_upper] = etf_data
                    save_etf_to_cache(ticker_upper, etf_data)
            except Exception as e:
                print(f"Errore download {ticker_upper}: {e}")
            
    with open(DATA_FILE, "w") as f:
        json.dump(market_data, f)

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Carichiamo all'avvio solo l'indice storico dei dati di mercato globali
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r") as f:
            global market_data
            market_data = json.load(f)
    yield

app = FastAPI(title="Portfolio ETF API Isolated", lifespan=lifespan)

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
    return {"error": "File index.html non trovato."}

# --- API Gestione Portafogli Isolate per Sessione ---

@app.post("/api/v1/portfolios")
def create_portfolio(portfolio: Portfolio, x_session_id: str = Header(None)):
    if not x_session_id:
        raise HTTPException(status_code=400, detail="Identificativo sessione mancante")
        
    total_weight = sum(a.weight for a in portfolio.assets)
    if abs(total_weight - 100.0) > 0.1:
        raise HTTPException(status_code=400, detail="La somma dei pesi deve essere 100%")
    
    for a in portfolio.assets:
        a.ticker = a.ticker.upper()

    # Carica, modifica e salva il file specifico di questa sessione
    session_portfolios = load_session_portfolios(x_session_id)
    session_portfolios[portfolio.name] = portfolio
    save_session_portfolios(x_session_id, session_portfolios)
    
    existing_tickers = set(market_data.keys())
    new_tickers = set(a.ticker for a in portfolio.assets) - existing_tickers
    if new_tickers:
        download_and_save_data(new_tickers)
        
    return {"message": "Portafoglio creato con successo"}

@app.get("/api/v1/portfolios")
def get_portfolios(x_session_id: str = Header(None)):
    if not x_session_id:
        return []
    session_portfolios = load_session_portfolios(x_session_id)
    return list(session_portfolios.keys())

@app.get("/api/v1/portfolios/{name}/composition")
def get_portfolio_composition(name: str, x_session_id: str = Header(None)):
    if not x_session_id:
        raise HTTPException(status_code=400, detail="Identificativo sessione mancante")
        
    session_portfolios = load_session_portfolios(x_session_id)
    if name not in session_portfolios:
        raise HTTPException(status_code=404, detail="Portafoglio non trovato in questa sessione")
    
    p = session_portfolios[name]
    assets_detail = [{"ticker": asset.ticker, "weight": asset.weight} for asset in p.assets]
    return {
        "portfolio": name,
        "assets": assets_detail,
        "total_weight": sum(a.weight for a in p.assets)
    }

@app.get("/api/v1/portfolios/{name}/history")
def get_portfolio_history(name: str, x_session_id: str = Header(None)):
    if not x_session_id:
        raise HTTPException(status_code=400, detail="Identificativo sessione mancante")
        
    session_portfolios = load_session_portfolios(x_session_id)
    if name not in session_portfolios:
        raise HTTPException(status_code=404, detail="Portafoglio non trovato")
    
    p = session_portfolios[name]
    dfs = []
    
    for asset in p.assets:
        if asset.ticker not in market_data:
            continue
        df = pd.DataFrame(market_data[asset.ticker])
        df.set_index('Date', inplace=True)
        df.rename(columns={'Close': asset.ticker}, inplace=True)
        dfs.append(df)
        
    if not dfs:
        raise HTTPException(status_code=404, detail="Dati non disponibili")
        
    merged = pd.concat(dfs, axis=1)
    merged.ffill(inplace=True)
    merged.dropna(inplace=True)
    
    portfolio_series = pd.Series(0.0, index=merged.index)
    for asset in p.assets:
        if asset.ticker in merged.columns:
            normalized_price = (merged[asset.ticker] / merged[asset.ticker].iloc[0]) * 100
            portfolio_series += normalized_price * (asset.weight / 100.0)
            
    result = [{"Date": date, "Value": round(val, 2)} for date, val in portfolio_series.items()]
    return {"portfolio": name, "data": result}

@app.get("/api/v1/portfolios/export")
def export_portfolios(x_session_id: str = Header(None)):
    """Esporta tutti i portafogli della sessione corrente in formato JSON"""
    if not x_session_id:
        raise HTTPException(status_code=400, detail="Identificativo sessione mancante")
        
    session_portfolios = load_session_portfolios(x_session_id)
    return session_portfolios

@app.post("/api/v1/portfolios/import")
def import_portfolios(imported_data: Dict[str, Portfolio], x_session_id: str = Header(None)):
    """Importa portafogli da un dizionario JSON"""
    if not x_session_id:
        raise HTTPException(status_code=400, detail="Identificativo sessione mancante")
        
    session_portfolios = load_session_portfolios(x_session_id)
    new_tickers = set()
    existing_tickers = set(market_data.keys())
    
    # Scorre i portafogli importati e li aggiunge alla sessione
    for name, portfolio in imported_data.items():
        # Forza uppercase per sicurezza
        for a in portfolio.assets:
            a.ticker = a.ticker.upper()
            if a.ticker not in existing_tickers:
                new_tickers.add(a.ticker)
        
        # Aggiunge o sovrascrive il portafoglio
        session_portfolios[name] = portfolio
        
    save_session_portfolios(x_session_id, session_portfolios)
    
    # Se ci sono nuovi ticker importati, scaricali e mettili in cache
    if new_tickers:
        download_and_save_data(new_tickers)
        
    return {"message": f"{len(imported_data)} portafogli importati con successo!"}

@app.get("/api/v1/etf-cache/status")
def get_etf_cache_status():
    cached_etfs = []
    if os.path.exists(ETF_CACHE_DIR):
        for file in os.listdir(ETF_CACHE_DIR):
            if file.endswith(".json"):
                ticker = file.replace(".json", "")
                file_size = os.path.getsize(os.path.join(ETF_CACHE_DIR, file))
                cached_etfs.append({"ticker": ticker, "cached": True, "file_size_bytes": file_size})
    return {"cached_etfs": cached_etfs, "total_cached": len(cached_etfs)}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)