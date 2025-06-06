# Switch Log Analyzer - Processo di Start e Parallelizzazione

## Sequenza di Start del Sistema

### 1. Fase di Inizializzazione (main.py)
```python
if __name__ == '__main__':
    # 1. Creazione directory logs
    os.makedirs('logs', exist_ok=True)
    
    # 2. Inizializzazione database
    create_tables()
    
    # 3. Inizializzazione scheduler
    scheduler.init_scheduler()
    scheduler.start()
    
    # 4. Caricamento job schedulati
    setup_scheduled_jobs()
    
    # 5. Registrazione cleanup
    atexit.register(lambda: scheduler.shutdown())
    
    # 6. Start Flask app
    app.run(host='0.0.0.0', port=5000, debug=False)
```

### 2. Dettaglio Fase Database (create_tables)
```python
def create_tables():
    with app.app_context():
        # Creazione tabelle PostgreSQL
        db.create_all()
        
        # Inizializzazione device lookup optimization
        device_lookup.refresh_index()
```

### 3. Dettaglio Fase Scheduler
#### Development Mode:
- Usa `ProductionSchedulerManager` con coordinamento file-based
- Worker designato tramite `/tmp/scheduler_worker.lock`
- Solo un worker gestisce lo scheduler

#### Production Mode (Gunicorn):
```bash
gunicorn -c gunicorn_config.py main:app
```
- Gestione multi-worker con file lock
- Worker PID più basso diventa scheduler worker
- Altri worker saltano l'inizializzazione scheduler

### 4. Caricamento Job Schedulati
```python
def setup_scheduled_jobs():
    # Carica job dal database
    scheduled_jobs = ScheduledJob.query.filter_by(enabled=True).all()
    
    for job in scheduled_jobs:
        if 'backup' in job.name.lower():
            # Job di backup
            scheduler.add_job(func=scheduled_backup_job)
        else:
            # Job di collection con credenziali
            scheduler.add_job(
                func=scheduled_collection_job,
                kwargs={'username': job.username, 'password': decrypted_password}
            )
```

## Sistema di Parallelizzazione Attuale

### Collection System (final_working_collector.py)
```python
def run_simple_collection(username, password):
    # Attualmente: 4 switch in parallelo
    with ThreadPoolExecutor(max_workers=4) as executor:
        futures = []
        for switch_info in switches:
            future = executor.submit(process_single_switch, switch_info, username, password)
            futures.append(future)
```

### Thread per Switch
Ogni switch processato in thread separato:
- Connessione SSH dedicata
- Session database thread-local
- Gestione errori indipendente
- Timeout configurabile

## Raccomandazioni per 8 Sessioni Parallele

### Configurazione Hardware Raccomandata

| Componente | Raccomandazione | Motivo |
|------------|-----------------|---------|
| **CPU Cores** | Minimo 8 core fisici (16 thread) | 1 core per switch + overhead sistema |
| **RAM** | Minimo 16GB | ~1GB per worker + database + cache |
| **Database Connections** | Pool di 20-30 connessioni | 8 switch + web workers + scheduler |
| **Network** | Connessione stabile 100Mbps+ | SSH simultanee verso 8 switch |

### Configurazione Gunicorn Raccomandata

```python
# gunicorn_config.py per 8 sessioni parallele
bind = "0.0.0.0:5000"
workers = 6  # 1 scheduler + 5 web workers
worker_class = "sync"
worker_connections = 10
max_requests = 1000
max_requests_jitter = 100
timeout = 300  # 5 minuti per collection lunghe
keepalive = 2
preload_app = True

# Memory management
max_memory_per_child = 512  # MB
worker_tmp_dir = "/tmp"

# Database pool
database_pool_size = 25
database_max_overflow = 10
```

### Modifiche Codice per 8 Switch

#### 1. Aggiornare ThreadPoolExecutor
```python
# In final_working_collector.py
def run_simple_collection(username, password):
    # Cambiare da 4 a 8 workers
    with ThreadPoolExecutor(max_workers=8) as executor:
        # resto del codice invariato
```

#### 2. Configurazione Database Pool
```python
# In main.py
app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
    "pool_size": 20,        # da 10 a 20
    "max_overflow": 15,     # da 5 a 15
    "pool_pre_ping": True,
    "pool_recycle": 300,
    "pool_timeout": 30
}
```

#### 3. Configurazione Scheduler
```python
# In production_scheduler_config.py
self.scheduler = BackgroundScheduler(
    job_defaults={
        'coalesce': False,
        'max_instances': 2,      # da 1 a 2
        'misfire_grace_time': 60  # da 30 a 60 secondi
    },
    executors={
        'default': {'type': 'threadpool', 'max_workers': 4}  # da 2 a 4
    }
)
```

### Monitoraggio Performance

#### Metriche da Monitorare:
1. **CPU Usage**: Non dovrebbe superare 80%
2. **Memory Usage**: Controllare memory leak sui worker
3. **Database Connections**: Pool utilization < 90%
4. **SSH Connection Time**: Timeout < 30 secondi per switch
5. **Collection Duration**: Tempo totale vs singolo switch

#### Script Monitoring
```bash
# Monitoring risorse durante collection
watch -n 5 'ps aux | grep -E "(gunicorn|python)" | head -20'
watch -n 5 'ss -tuln | grep :5000'
```

### Rischi e Mitigazioni

| Rischio | Impatto | Mitigazione |
|---------|---------|-------------|
| **Memory Leak** | Alto | Worker restart automatico |
| **Database Lock** | Alto | Connection pool + timeout |
| **SSH Timeout** | Medio | Retry logic + timeout configuration |
| **Switch Overload** | Medio | Rate limiting + connection spacing |
| **Disk I/O** | Basso | SSD storage + log rotation |

### Test Raccomandati Prima del Deploy

1. **Load Testing**: Simulare 8 collection simultanee
2. **Memory Profiling**: Verificare uso memoria per 30+ minuti
3. **Database Stress**: Test con 20+ connessioni simultanee
4. **Network Stability**: Test connessioni SSH lunghe
5. **Failover Testing**: Test recupero da errori switch

### Conclusione

Per 8 sessioni parallele raccomando:
- **6 Gunicorn workers** (1 scheduler + 5 web)
- **Minimo 8 core CPU** e **16GB RAM**
- **Pool database di 25 connessioni**
- **Monitoring attivo** delle risorse
- **Test graduale** partendo da 6 switch poi scalando a 8

Il sistema attuale è già progettato per scalare, servono principalmente aggiustamenti di configurazione numerica.
