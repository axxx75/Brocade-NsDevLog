# 📚 Brocade NsDevLog (Switch Log Analyzer)
An advanced log analysis system for Brocade fibrechannel switches that collects, processes and analyzes "nsdevlog" event logs through automated SSH connections with scheduling and optimized lookup capabilities to integrate additional debug data that the command does not display.

This documentation provides a comprehensive overview of the architecture and functionality of the Switch Log Analyzer, facilitating maintenance, troubleshooting and future extensions of the system.

- [Project Structure](PROJECT_STRUCTURE.md)
- [Database](DATABASE.md)

# NSDevLog
NSDevLog (Name Server Device Log) is a Brocade switch FOS command used to monitor devices in the SAN fabric.
It is a local log of events related to devices (N_Ports) that connect to or disconnect from the switch (PLOGIN/PLOGOUT).
It tracks changes to the Name Server (NS) database, the service that maps devices in the fabric.

- [Doc brocade](https://techdocs.broadcom.com/us/en/fibre-channel-networking/fabric-os/fabric-os-commands/9-2-x/Fabric-OS-Commands/nsDevLog.html)


## 🏗️ System Architecture

### Frontend Architecture
- **Web Framework**: Flask with Jinja2 templating
- **UI Components**: Bootstrap 5 with FontAwesome icons
- **Templates**: 
  - `index.html` - Main search interface with filtering and pagination
  - `maintenance.html` - Database management and health monitoring
  - `scheduler.html` - Job scheduling and credential management
- **Client-side Features**: Real-time status updates, AJAX-based collection monitoring, CSV export functionality

### Backend Architecture
- **Application Server**: Gunicorn WSGI server with 2-worker architecture
- **Framework**: Flask with SQLAlchemy ORM
- **Scheduler**: APScheduler isolated to Worker 1 only
- **Collection Engine**: SSH-based log collection on Worker 2 with dynamic spawning
- **Authentication**: SSH-based switch authentication with configurable credentials

### Data Storage Solutions
- **Primary Database**: PostgreSQL with optimized composite indexes
- **Cache Layer**: SQLite for device lookup optimization with LRU caching
- **File Storage**: JSON-based temporary files and native Python backups

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

## 🔄 Workflow

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

### Collection Operations
- `POST /api/collect/credentials` - Avvia raccolta con credenziali custom
- `GET /api/collection/status` - Status real-time raccolta attiva
- `GET /api/collections` - Lista raccolte recenti con metadata

### Database Management
- `GET /api/db/search` - Ricerca avanzata con parametri filtro
- `GET /api/db/stats` - Statistiche database e performance metrics
- `GET /api/export-csv` - Export CSV risultati ricerca

### Scheduler Administration
- `GET /api/scheduler/status` - Status scheduler e job attivi
- `POST /api/scheduler/jobs` - Crea job schedulato con cron expression
- `DELETE /api/scheduler/jobs/<id>` - Rimuovi job specifico

### Maintenance
- `POST /api/db/backup` - Backup nativo database compresso
- `POST /api/db/collections/cleanup` - Cleanup collezioni stuck
- `GET /api/device-lookup/stats` - Statistiche device lookup optimization

## ⚙️ Configuration

### Switch Configuration (`switches.conf`)
```
# Format: site:hostname:generation
to:switch1:gen6
mi:switch2:gen7
```

### Environment Variables (`.env`)
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

### Scheduler Issues
```bash
# Verifica single-worker scheduler
journalctl -u nsdevlog.service | grep "Single worker mode"

# Monitor job execution
journalctl -u nsdevlog.service | grep "Running job"
```

### Collection Monitoring
```bash
# Status raccolta corrente
curl localhost:5000/api/collection/status

# Health database
curl localhost:5000/api/db/health

# Statistics device lookup
curl localhost:5000/api/device-lookup/stats
```

### Log Analysis
```bash
# Comprehensive monitoring
journalctl -u nsdevlog.service -f | grep -E "(SCHEDULER|device_port|collection run)"

# Error tracking
journalctl -u nsdevlog.service | grep ERROR | tail -20
```

## 🛠️ External Dependencies
### Infrastructure Dependencies
- **PostgreSQL**: Primary database (configured via DATABASE_URL)
- **Docker/Podman**: Container runtime for SanNav integration
- **SystemD**: Service management for production deployment

### Python Dependencies
- **Flask**: Web framework and API development
- **SQLAlchemy**: ORM and database abstraction
- **Paramiko**: SSH client for switch connections
- **APScheduler**: Background job scheduling
- **psycopg2-binary**: PostgreSQL database adapter

### Network Dependencies
- **Switch Inventory**: Configuration file (`switches.conf`) with switch hostnames
- **SSH Credentials**: Environment variables for switch authentication
- **SanNav Container**: External container for authentic device port data

## Quick Start
```bash
# Clone repository in desired folder
git clone https://github.com/axxx75/Brocade-NsDevLog.git

# Deploy App enviroments
sh _deploy_production.sh setup

# Setup database
Database can create in deployment_production procedure

# Configure switches
vi switches.conf

# Start application
systemctl start nsdevlog
```

### Common Issues
- **SSH timeouts**: Verifica connettività e credenziali switch
- **Database locks**: Monitor connessioni attive PostgreSQL  
- **Memory usage**: Monitora utilizzo durante raccolte grandi
- **Stuck collections**: Usa force cleanup per sbloccare

## 🙌 Contributing
Pull request e issue sono benvenute! Per segnalare problemi o proporre funzionalità, apri una issue o unisciti allo sviluppo.
