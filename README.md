# ETF Dashboard & API Service 📈

Questo progetto fornisce un servizio completo per monitorare l'andamento degli ETF (come `SWDA.MI`). Include un'API RESTful per i dati storici e una Dashboard web interattiva integrata.

---

## 🚀 Novità in questa versione

- **Web Dashboard**: Accessibile direttamente dalla root del server.
- **VM Ready**: Configurato per accettare connessioni esterne (ottimo per VirtualBox, VMware, VPS).
- **Zero Configuration**: Il backend serve automaticamente il frontend.
- **Cache Locale ETF**: I dati degli ETF vengono salvati in locale e riutilizzati senza scaricamenti ripetuti dal cloud.

---

## ⚙️ Installazione

1. Installa le dipendenze:
   ```bash
   pip install -r requirements.txt
   ```

2. Avvia il server:
   ```bash
   python app.py
   ```

3. Accedi alla dashboard:
   - Locale: `http://localhost:8000`
   - Rete: `http://<IP_MACHINE>:8000`

---

## 💾 Sistema di Cache Locale

### Come Funziona

- **Primo utilizzo**: Quando inserisci un ETF in un portafoglio, il sistema scarica i dati da Yahoo Finance e li **salva automaticamente** nella cartella `etf_data/`
- **Utilizzi successivi**: Se lo stesso ETF viene utilizzato nuovamente, il sistema **carica i dati da locale** senza scaricarli di nuovo dal cloud
- **Organizzazione**: Ogni ETF è salvato in un file separato: `etf_data/TICKER.json`

### Endpoint di Gestione Cache

#### Verificare lo stato della cache
```bash
GET /api/v1/etf-cache/status
```
Ritorna la lista degli ETF salvati localmente con relative dimensioni.

**Esempio di risposta:**
```json
{
  "cached_etfs": [
    {"ticker": "SWDA.MI", "cached": true, "file_size_bytes": 45000},
    {"ticker": "EIMI.MI", "cached": true, "file_size_bytes": 43000}
  ],
  "total_cached": 2
}
```

#### Pulire la cache di un ETF specifico
```bash
POST /api/v1/etf-cache/clear/{ticker}
```
Rimuove l'ETF dalla cache locale. Alla prossima creazione di un portafoglio con questo ticker, i dati verranno riscaricati.

**Esempio:**
```bash
curl -X POST http://localhost:8000/api/v1/etf-cache/clear/SWDA.MI
```

### Dashboard - Sezione Cache

Nella dashboard web è presente una sezione "Cache ETF Locale" che permette di:
- Verificare quali ETF sono già salvati localmente
- Visualizzare lo spazio occupato da ogni ETF
- Aggiornare lo stato della cache in tempo reale

---

## 📊 API Endpoints

### Portafogli
- `POST /api/v1/portfolios` - Crea un nuovo portafoglio
- `GET /api/v1/portfolios` - Elenca tutti i portafogli
- `GET /api/v1/portfolios/{name}/history` - Ottiene la curva di rendimento

### Cache ETF
- `GET /api/v1/etf-cache/status` - Stato della cache locale
- `POST /api/v1/etf-cache/clear/{ticker}` - Rimuove un ETF dalla cache

---

## 📁 Struttura dei File

```
.
├── app.py                 # Backend FastAPI
├── index.html             # Frontend Dashboard
├── portfolios.json        # Dati dei portafogli salvati
├── market_data.json       # Indice dei dati scaricati
├── etf_data/              # Cartella di cache locale per gli ETF
│   ├── SWDA.MI.json       # Dati storici SWDA.MI
│   ├── EIMI.MI.json       # Dati storici EIMI.MI
│   └── ...
└── requirements.txt       # Dipendenze Python
```

---

## 🔄 Flusso di Utilizzo

1. **Crea un portafoglio** nella dashboard aggiungendo ETF e pesi
2. **First download**: Il sistema scarica i dati da Yahoo Finance e li salva in `etf_data/`
3. **Salvataggio locale**: I dati rimangono in cache per usi futuri
4. **Visualizzazione**: Puoi visualizzare la curva di rendimento del portafoglio
5. **Riutilizzo**: Se aggiungi lo stesso ETF a un altro portafoglio, i dati vengono caricati da locale (veloce!)

---

## 📈 Esempio di Portafoglio

```json
{
  "name": "Globale Diversificato",
  "assets": [
    {"ticker": "SWDA.MI", "weight": 60},
    {"ticker": "EIMI.MI", "weight": 40}
  ]
}
```

---

## 🛠️ Tecnologie Utilizzate

- **Backend**: FastAPI, Python, Pandas
- **Data Source**: Yahoo Finance (yfinance)
- **Frontend**: HTML, CSS, Chart.js
- **Server**: Uvicorn