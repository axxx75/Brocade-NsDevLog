# Switch Log Analyzer

Un sistema avanzato di analisi log per switch fibrechannel Brocade che raccoglie, elabora e analizza i log di eventi "nsdevlog" attraverso connessioni SSH automatizzate con funzionalità di scheduling intelligente e lookup ottimizzato.

# NSDevLog
loremipsum....loremipsum


## 🏗️ Architettura del Sistema

```mermaid
graph TB
    subgraph "Frontend Web Interface"
        A[Database Search Interface] --> B[Scheduler Admin Panel]
        B --> C[Maintenance Dashboard]
    end
    
    subgraph "Flask Application (main.py)"
        D[REST API Endpoints] --> E[Background Scheduler]
        E --> F[Collection Orchestrator]
    end
    
    subgraph "Collection System"
        F --> G[Simple Switch Collector]
        G --> H[Final Working Collector]
        H --> I[Device Lookup Optimizer]
    end
    
    subgraph "Data Layer"
        I --> J[PostgreSQL Database]
        I --> K[SQLite Device Cache]
        L[Switch Configuration] --> G
    end
    
    subgraph "External Systems"
        M[Brocade Switches] --> G
        N[Device Port JSON] --> I
    end
    
    A --> D
    C --> D
    J --> A
    K --> I
```

## 🔧 Componenti Principali

### Core Files

| File | Funzione | Descrizione |
|------|----------|-------------|
| `main.py` | **Controller Principale** | Flask app con API REST, scheduler background e gestione delle route |
| `models.py` | **Database Schema** | Modelli SQLAlchemy per PostgreSQL con indici ottimizzati |
| `config.py` | **Configurazione** | Settings essenziali e caricamento lista switch |

### Collection Engine

| File | Funzione | Descrizione |
|------|----------|-------------|
| `simple_switch_collector.py` | **Motore Base** | Connessione SSH singola, parsing log, gestione timestamp |
| `final_working_collector.py` | **Orchestratore Parallelo** | Coordinamento 4-8 worker simultanei, gestione database |
| `device_lookup_optimized.py` | **Lookup Intelligente** | Cache SQLite + LRU, logica NPIV avanzata |

### Configuration

| File | Funzione | Descrizione |
|------|----------|-------------|
| `switches.conf` | **Lista Switch** | Configurazione switch nel formato `site:hostname:generation` |
| `.env` | **Environment** | Credenziali database e variabili ambiente |

## 🔄 Flusso di Lavoro

### 1. Collection Process
```
User Triggers Collection
    ↓
Final Working Collector
    ↓
ThreadPoolExecutor (4-8 workers)
    ↓
Per ogni switch in parallelo:
    ├── Simple Switch Collector
    ├── SSH Connection
    ├── nsdevlog --show execution
    ├── Log parsing & timestamp fix
    ├── Device lookup (alias/node_symbol)
    └── Database insertion
    ↓
Consolidation & Status Update
```

### 2. Device Lookup Intelligence
```
Log Entry (WWN + Switch + Port)
    ↓
SQLite Index Lookup
    ↓
NPIV Detection Logic:
├── WWN == physicalPortWwn? → Use virtual symbolicName
└── WWN != physicalPortWwn? → Use physical port symbolicName
    ↓
LRU Cache Storage
    ↓
Return (alias, node_symbol)
```

### 3. Scheduled Collections
```
Database-Persisted Jobs
    ↓
APScheduler Background
    ↓
Cron Trigger Execution
    ↓
Automatic Collection Launch
    ↓
Result Logging & Notification
```

## 📊 Database Schema

### LogEntry (Tabella Principale)
- **Indici ottimizzati**: timestamp+switch, WWN+timestamp, alias, node_symbol
- **Campi chiave**: timestamp, switch_name, context, event_type, wwn, alias, node_symbol
- **Performance**: Supporta milioni di record con query sub-secondo

### CollectionRun (Tracking Esecuzioni)
- **Status tracking**: running → completed/failed
- **Metadata**: switch processati, entry totali/nuove, tempi esecuzione
- **Error handling**: Messaggi errore dettagliati

### ScheduledJob (Jobs Persistenti)
- **Cron scheduling**: Espressioni cron per automazione
- **Credential management**: Username/password per switch
- **Enable/disable**: Controllo attivazione jobs

## 🎯 Funzionalità Avanzate

### Intelligent NPIV Handling
Il sistema riconosce automaticamente i dispositivi NPIV (N_Port ID Virtualization):
- **Virtual WWN**: Quando WWN ≠ physicalPortWwn, restituisce il symbolicName della porta fisica
- **Physical WWN**: Utilizza direttamente il symbolicName della porta virtuale
- **Performance**: Lookup cache con LRU per velocità ottimale

### Parallel Processing
- **4-8 worker threads**: Elaborazione simultanea di più switch
- **Thread-safe database**: Sessioni separate per ogni worker
- **Error isolation**: Fallimento di un switch non compromette gli altri

### Smart Timestamp Handling
- **Year deduction**: Algoritmo intelligente per aggiungere anni ai timestamp
- **Boundary detection**: Riconoscimento automatico di passaggi d'anno nei log
- **Chronological sorting**: Ordinamento temporale accurato

## 🔍 Search & Export Capabilities

### Advanced Filtering
- **Multi-field search**: WWN, alias, node_symbol, switch_name, event_type
- **Date range filtering**: Ricerca temporale precisa
- **Pagination**: Gestione efficiente di grandi dataset
- **Sorting**: Ordinamento su qualsiasi colonna

### Export Functionality
- **CSV Export**: Esportazione completa dei risultati filtrati
- **Real-time generation**: Streaming CSV per grandi dataset
- **Custom headers**: Campi personalizzabili per export

## 🚀 API Endpoints

### Core Operations
- `POST /api/db/collect` - Avvia raccolta log
- `GET /api/db/search` - Ricerca nel database
- `GET /api/collection/status` - Status raccolta in corso
- `GET /api/export-csv` - Esporta risultati ricerca

### Administration
- `GET /api/scheduler/status` - Status scheduler
- `POST /api/scheduler/jobs` - Crea job schedulato
- `DELETE /api/scheduler/jobs/<id>` - Rimuovi job
- `POST /api/db/backup` - Crea backup database

### Maintenance
- `GET /api/db/stats` - Statistiche database
- `GET /api/db/health` - Salute sistema
- `POST /api/db/collections/cleanup` - Pulizia collezioni bloccate

## ⚙️ Configuration

### Switch Configuration (`switches.conf`)
```
# Format: site:hostname:generation
ccm:ccmfcp2:gen6
ccm:santgtccm4:gen7
ccm:santgtccm6:gen7
```

### Environment Variables
```bash
DATABASE_URL=postgresql://user:pass@host:port/database
SWITCH_USERNAME=username
SWITCH_PASSWORD=password
SECRET_KEY=your-secret-key
```

## 🔧 Performance Optimizations

### Database Level
- **Composite indexes**: Ottimizzati per query comuni
- **Connection pooling**: Pool size 10 con pre-ping
- **Batch operations**: Inserimenti in lotti per performance

### Application Level
- **LRU Caching**: Device lookup con cache 10K entries
- **SQLite indexing**: Lookup device sub-millisecondo
- **Parallel processing**: Fino a 8 switch simultanei

### Memory Management
- **Streaming JSON**: Processing file grandi con memory mapping
- **Thread-local sessions**: Isolamento memoria per worker
- **Garbage collection**: Cleanup automatico risorse

## 📈 Monitoring & Logs

### Application Logs
- **Structured logging**: Timestamp, level, component, messaggio
- **File rotation**: Log persistenti in directory `logs/`
- **Real-time monitoring**: Console output per debug

### Collection Metrics
- **Performance tracking**: Tempi esecuzione per switch
- **Success rates**: Statistiche successo/fallimento
- **Data volume**: Conteggi entry nuove/duplicate

## 🛠️ Deployment

### Requirements
- Python 3.11+
- PostgreSQL 12+
- SSH access ai switch Brocade
- Device port JSON file (per device lookup)

### Quick Start
```bash
# Install dependencies
pip install -r requirements.txt

# Setup database
export DATABASE_URL="postgresql://..."

# Configure switches
vi switches.conf

# Start application
python main.py
```

### Production Considerations
- **WSGI server**: Usa Gunicorn invece del dev server
- **Database tuning**: Ottimizza parametri PostgreSQL
- **Monitoring**: Implementa health checks
- **Security**: HTTPS, credential encryption, firewall rules

## 📚 Troubleshooting

### Common Issues
- **SSH timeouts**: Verifica connettività e credenziali switch
- **Database locks**: Monitor connessioni attive PostgreSQL  
- **Memory usage**: Monitora utilizzo durante raccolte grandi
- **Stuck collections**: Usa force cleanup per sbloccare

### Debug Mode
```bash
export DEBUG=true
python main.py
```

### Log Analysis
```bash
# Monitor application logs
tail -f logs/app.log

# Check collection status
curl localhost:5000/api/collection/status

# Database health
curl localhost:5000/api/db/health
```

Questa documentazione fornisce una panoramica completa dell'architettura e delle funzionalità del Switch Log Analyzer, facilitando manutenzione, troubleshooting e future estensioni del sistema.
