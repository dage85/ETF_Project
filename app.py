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

PORTFOLIOS_FILE = "portfolios.json"
DATA_FILE = "market_data.json"

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

def download_and_save_data(tickers: set):
    """Scarica i dati da YF e li salva in locale"""
    global market_data
    
    # Carica i dati esistenti se ci sono, per non sovrascrivere tutto se aggiungiamo 1 solo ticker
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r") as f:
            market_data = json.load(f)
            
    for ticker in tickers:
        print(f"Scaricamento dati per {ticker}...")
        asset = yf.Ticker(ticker)
        # Scarichiamo 5 anni di default per avere uno storico decente per i portafogli
        hist = asset.history(period="5y") 
        if not hist.empty:
            hist.reset_index(inplace=True)
            hist['Date'] = hist['Date'].dt.strftime('%Y-%m-%d')
            market_data[ticker] = hist[['Date', 'Close']].to_dict(orient="records")
        else:
            print(f"ATTENZIONE: Nessun dato trovato per {ticker}")
            
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