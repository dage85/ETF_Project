import yfinance as yf
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
import uvicorn
import os

app = FastAPI(title="ETF API")

# Abilita CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], 
    allow_methods=["*"],
    allow_headers=["*"],
)

# Endpoint per servire la pagina HTML principale
@app.get("/")
def serve_frontend():
    # Cerca il file index.html nella stessa cartella dello script
    file_path = os.path.join(os.path.dirname(__file__), "index.html")
    if os.path.exists(file_path):
        return FileResponse(file_path)
    return {"error": "File index.html non trovato nella cartella."}

# L'API per i dati (rimasta invariata)
@app.get("/api/v1/history/{ticker}")
def get_etf_history(ticker: str, period: str = Query("1y")):
    try:
        asset = yf.Ticker(ticker)
        hist = asset.history(period=period)
        if hist.empty:
            raise HTTPException(status_code=404, detail="Dati non trovati")
        
        hist.reset_index(inplace=True)
        hist['Date'] = hist['Date'].dt.strftime('%Y-%m-%d')
        data = hist.to_dict(orient="records")
        
        return {"ticker": ticker.upper(), "data": data}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    # ATTENZIONE: host impostato su "0.0.0.0" per permettere l'accesso dall'esterno della VM
    print("Server in avvio...")
    uvicorn.run(app, host="0.0.0.0", port=8000)