import yfinance as yf
from fastapi import FastAPI, HTTPException, Header
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel
import uvicorn
import os
import json
import pandas as pd
import numpy as np
from pathlib import Path
from typing import List, Dict

# Cartelle per dati globali e dati di sessione
SESSION_DIR = "portfolios_sessions"
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


# --- Funzioni Helper per la Sessione ---
def get_session_file(session_id: str) -> str:
    safe_id = "".join(c for c in session_id if c.isalnum() or c in "-_")
    return os.path.join(SESSION_DIR, f"portfolios_{safe_id}.json")

def load_session_portfolios(session_id: str) -> dict:
    file_path = get_session_file(session_id)
    if os.path.exists(file_path):
        with open(file_path, "r") as f:
            data = json.load(f)
            portfolios = {k: Portfolio(**v) for k, v in data.items()}
            
            missing_tickers = set()
            for p in portfolios.values():
                for asset in p.assets:
                    ticker_upper = asset.ticker.upper()
                    if not etf_exists_locally(ticker_upper):
                        missing_tickers.add(ticker_upper)
            
            if missing_tickers:
                print(f"🔍 Rilevati ticker salvati ma assenti in cache: {missing_tickers}. Avvio recupero dati...")
                download_and_save_data(missing_tickers)
                
            return portfolios
    return {}

def save_session_portfolios(session_id: str, portfolios: dict):
    file_path = get_session_file(session_id)
    with open(file_path, "w") as f:
        json.dump({k: v.dict() for k, v in portfolios.items()}, f)


# --- Funzioni di Cache ETF ---
def get_etf_cache_path(ticker: str) -> str:
    return os.path.join(ETF_CACHE_DIR, f"{ticker.upper()}.json")

def etf_exists_locally(ticker: str) -> bool:
    return os.path.exists(get_etf_cache_path(ticker))

def load_etf_from_cache(ticker: str) -> list:
    try:
        with open(get_etf_cache_path(ticker), "r") as f:
            return json.load(f)
    except Exception as e:
        print(f"Errore cache per {ticker}: {e}")
        return []

def save_etf_to_cache(ticker: str, data: list):
    try:
        with open(get_etf_cache_path(ticker), "w") as f:
            json.dump(data, f)
    except Exception as e:
        print(f"Errore salvataggio cache per {ticker}: {e}")

def download_and_save_data(tickers: set):
    for ticker in tickers:
        ticker_upper = ticker.upper()
        if etf_exists_locally(ticker_upper):
            continue
            
        try:
            asset = yf.Ticker(ticker_upper)
            hist = asset.history(period="10y")
            if not hist.empty:
                hist.reset_index(inplace=True)
                
                # Risoluzione anomalie indici di YFinance
                if 'Date' not in hist.columns:
                    if 'Datetime' in hist.columns:
                        hist.rename(columns={'Datetime': 'Date'}, inplace=True)
                    elif 'index' in hist.columns:
                        hist.rename(columns={'index': 'Date'}, inplace=True)
                
                # Conversione data in formato pulito ignorando problematiche di TimeZone
                hist['Date'] = pd.to_datetime(hist['Date'], utc=True).dt.strftime('%Y-%m-%d')
                
                etf_data = hist[['Date', 'Close']].to_dict(orient="records")
                save_etf_to_cache(ticker_upper, etf_data)
                print(f"✅ Dati scaricati e salvati in cache per: {ticker_upper}")
        except Exception as e:
            print(f"❌ Errore download {ticker_upper}: {e}")


# --- FUNZIONE HELPER ROBUSTA PER UNIRE I DATI DEL PORTAFOGLIO ---
def get_portfolio_df(portfolio: Portfolio) -> pd.DataFrame:
    dfs = []
    for asset in portfolio.assets:
        ticker = asset.ticker.upper()
        if etf_exists_locally(ticker):
            etf_data = load_etf_from_cache(ticker)
            if etf_data:
                df = pd.DataFrame(etf_data)
                if 'Date' in df.columns and 'Close' in df.columns:
                    df.set_index('Date', inplace=True)
                    df.rename(columns={'Close': ticker}, inplace=True)
                    df = df[~df.index.duplicated(keep='last')]
                    dfs.append(df)
    
    if not dfs:
        return pd.DataFrame()
        
    merged = pd.concat(dfs, axis=1)
    
    # FONDAMENTALE: Ordina l'indice cronologicamente PRIMA di applicare le logiche di filling
    merged.sort_index(inplace=True) 
    
    merged.ffill(inplace=True)
    merged.dropna(inplace=True)
    return merged


# --- Inizializzazione FastAPI ---
app = FastAPI(title="Portfolio ETF API Isolated")

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


# --- API Gestione Portafogli ---

@app.post("/api/v1/portfolios")
def create_portfolio(portfolio: Portfolio, x_session_id: str = Header(None)):
    if not x_session_id:
        raise HTTPException(status_code=400, detail="Identificativo sessione mancante")
        
    total_weight = sum(a.weight for a in portfolio.assets)
    if abs(total_weight - 100.0) > 0.1:
        raise HTTPException(status_code=400, detail="La somma dei pesi deve essere 100%")
    
    for a in portfolio.assets:
        a.ticker = a.ticker.upper()

    session_portfolios = load_session_portfolios(x_session_id)
    session_portfolios[portfolio.name] = portfolio
    
    new_tickers = set(a.ticker for a in portfolio.assets if not etf_exists_locally(a.ticker))
    if new_tickers:
        download_and_save_data(new_tickers)
        
    save_session_portfolios(x_session_id, session_portfolios)
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
        raise HTTPException(status_code=404, detail="Portafoglio non trovato")
    
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
    merged = get_portfolio_df(p)
    
    if merged.empty:
        raise HTTPException(status_code=404, detail="Dati insufficienti o date non allineate (verifica lo storico degli ETF).")
        
    portfolio_series = pd.Series(0.0, index=merged.index)
    for asset in p.assets:
        ticker = asset.ticker.upper()
        if ticker in merged.columns:
            first_val = merged[ticker].iloc[0]
            if first_val == 0: first_val = 1e-9 # Previene divisione per zero
            normalized_price = (merged[ticker] / first_val) * 100
            portfolio_series += normalized_price * (asset.weight / 100.0)
            
    portfolio_series.fillna(0, inplace=True)
    
    # Assicura serializzazione sicura: converte sempre la data a stringa pura e il valore a float pulito
    result = [{"Date": str(date)[:10], "Value": round(float(val), 2)} for date, val in portfolio_series.items()]
    
    return {"portfolio": name, "data": result}


# --- Endpoint di Benchmark ---
@app.get("/api/v1/benchmark")
def run_benchmark(p1: str, p2: str, rolling_years: int = 5, x_session_id: str = Header(None)):
    if not x_session_id:
        raise HTTPException(status_code=400, detail="Identificativo sessione mancante")
        
    session_portfolios = load_session_portfolios(x_session_id)
    if p1 not in session_portfolios or p2 not in session_portfolios:
        raise HTTPException(status_code=404, detail="Portafogli non trovati")

    port1 = session_portfolios[p1]
    port2 = session_portfolios[p2]

    df1 = get_portfolio_df(port1)
    df2 = get_portfolio_df(port2)

    if df1.empty or df2.empty:
        raise HTTPException(status_code=400, detail="Dati non sufficienti per eseguire il benchmark.")

    common_dates = df1.index.intersection(df2.index)
    if len(common_dates) < 2:
        raise HTTPException(status_code=400, detail="Periodo storico in comune troppo breve (meno di 2 giorni).")

    df1 = df1.loc[common_dates]
    df2 = df2.loc[common_dates]

    def calc_portfolio_series(df, portfolio):
        series = pd.Series(0.0, index=df.index)
        for asset in portfolio.assets:
            ticker = asset.ticker.upper()
            if ticker in df.columns:
                first_val = df[ticker].iloc[0]
                if first_val == 0: first_val = 1e-9
                norm = df[ticker] / first_val
                series += norm * (asset.weight / 100.0)
        return series

    series1 = calc_portfolio_series(df1, port1)
    series2 = calc_portfolio_series(df2, port2)

    window = rolling_years * 252

    def compute_rolling_data(series):
        ret = series.pct_change(periods=window)
        
        daily_returns = series.pct_change()
        vol = daily_returns.rolling(window=window).std() * np.sqrt(252)
        sharpe = ret / vol
        
        def mdd(x):
            peaks = np.maximum.accumulate(x)
            drawdowns = (x - peaks) / peaks
            return np.min(drawdowns) if len(drawdowns) > 0 else 0
            
        mdd_series = series.rolling(window=window).apply(mdd, raw=True)
        
        return {
            "rolling_return": [x if pd.notna(x) and not np.isinf(x) else None for x in ret],
            "rolling_sharpe": [x if pd.notna(x) and not np.isinf(x) else None for x in sharpe],
            "rolling_mdd": [x if pd.notna(x) and not np.isinf(x) else None for x in mdd_series]
        }

    roll1 = compute_rolling_data(series1)
    roll2 = compute_rolling_data(series2)

    def compute_metrics(series):
        returns = series.pct_change().dropna()
        if returns.empty: return {}

        total_return = (series.iloc[-1] / series.iloc[0]) - 1
        days = len(series)
        years = days / 252
        
        cagr = ((1 + total_return) ** (1 / years) - 1) if years > 0 and (1 + total_return) > 0 else 0
        volatility = returns.std() * np.sqrt(252)
        sharpe = cagr / volatility if volatility > 0 else 0
        
        downside_returns = returns[returns < 0]
        downside_std = downside_returns.std() * np.sqrt(252) if len(downside_returns) > 0 else 0
        sortino = cagr / downside_std if downside_std > 0 else 0
        
        running_max = series.cummax()
        drawdown = (series - running_max) / running_max
        max_dd = drawdown.min()
        
        calmar = cagr / abs(max_dd) if max_dd < 0 else 0
        
        var_95 = returns.quantile(0.05)
        var_99 = returns.quantile(0.01)
        
        pos_days = (returns > 0).mean()
        
        rolling_1y = series.pct_change(periods=min(252, len(series)-1)).dropna()
        pos_roll = (rolling_1y > 0).mean() if not rolling_1y.empty else 0
        
        return {
            "Total Return": f"{total_return*100:.2f}%",
            "CAGR": f"{cagr*100:.2f}%",
            "Volatility": f"{volatility*100:.2f}%",
            "Sharpe": f"{sharpe:.2f}",
            "Sortino": f"{sortino:.2f}",
            "Max Drawdown": f"{max_dd*100:.2f}%",
            "Calmar": f"{calmar:.2f}",
            "VaR 95": f"{var_95*100:.2f}%",
            "VaR 99": f"{var_99*100:.2f}%",
            "% Giorni Positivi": f"{pos_days*100:.2f}%",
            "% Rolling Positivi": f"{pos_roll*100:.2f}%"
        }

    res1 = compute_metrics(series1)
    res2 = compute_metrics(series2)
    
    return {
        "metrics": list(res1.keys()),
        "p1_name": p1,
        "p2_name": p2,
        "p1_results": res1,
        "p2_results": res2,
        "charts": {
            "dates": series1.index.tolist(),
            "p1": roll1,
            "p2": roll2
        }
    }

@app.get("/api/v1/portfolios/export")
def export_portfolios(x_session_id: str = Header(None)):
    if not x_session_id:
        raise HTTPException(status_code=400, detail="Identificativo sessione mancante")
    return load_session_portfolios(x_session_id)

@app.post("/api/v1/portfolios/import")
def import_portfolios(imported_data: Dict[str, Portfolio], x_session_id: str = Header(None)):
    if not x_session_id:
        raise HTTPException(status_code=400, detail="Identificativo sessione mancante")
        
    session_portfolios = load_session_portfolios(x_session_id)
    missing_tickers = set()
    
    for name, portfolio in imported_data.items():
        for a in portfolio.assets:
            a.ticker = a.ticker.upper()
            if not etf_exists_locally(a.ticker):
                missing_tickers.add(a.ticker)
        session_portfolios[name] = portfolio
        
    save_session_portfolios(x_session_id, session_portfolios)
    
    if missing_tickers:
        download_and_save_data(missing_tickers)
        
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

@app.post("/api/v1/etf-cache/clear/{ticker}")
def clear_etf_cache(ticker: str):
    ticker = ticker.upper()
    cache_path = get_etf_cache_path(ticker)
    if os.path.exists(cache_path):
        os.remove(cache_path)
        return {"message": f"Cache per {ticker} eliminata"}
    raise HTTPException(status_code=404, detail=f"ETF {ticker} non trovato in cache")

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)