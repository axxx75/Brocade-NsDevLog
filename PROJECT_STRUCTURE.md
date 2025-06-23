# Switch Log Analyzer - Project Structure

## Active Files Documentation

| File | Purpose | Classes/Functions | Description |
|------|---------|-------------------|-------------|
| **main.py** | Main Flask Application | `MockScheduler`, `cleanup_temporary_log_files()`, `create_native_backup()`, `scheduled_backup_job()`, `scheduled_collection_job()`, `setup_scheduled_jobs()`, `verify_scheduler_health()`, `create_tables()`, multiple route handlers | Core web application with single-worker scheduler integration, database operations, and comprehensive API endpoints |
| **models.py** | Database Models | `LogEntry`, `CollectionRun`, `AliasMapping`, `SwitchStatus`, `AppConfig`, `ScheduledJob` | PostgreSQL database models with optimized composite indexes for efficient log storage and retrieval |
| **final_working_collector.py** | Parallel Collection Engine | `get_thread_db_session()`, `process_single_switch()`, `run_simple_collection()` | Parallel 4-switch log collection with thread-safe PostgreSQL integration and error isolation |
| **device_lookup_optimized.py** | Authentic Device Lookup | `DeviceLookupOptimized`, `extract_slot_port_from_entry()`, `lookup_alias_and_node_symbol()`, `refresh_device_port_data()` | SQLite-indexed device lookup with authentic SanNav container data access, LRU cache, and NPIV intelligence |
| **simple_switch_collector.py** | SSH Collection Base | `SimpleLogCollector`, `connect_to_switch()`, `collect_from_context_simple()`, `parse_log_line()`, `fix_timestamps_with_years()` | Individual switch SSH connection handler with intelligent timestamp processing and log parsing |
| **config.py** | Application Configuration | `Config`, `Config.load_switches()` | Environment-based configuration management with switch inventory loading |
| **simple_direct_scheduler.py** | Single-Worker Scheduler | `on_starting(server)`,`when_ready(server)`, `worker_int(worker)`, `pre_fork(server, worker)`, `post_fork(server, worker)`, `worker_abort(worker)`  | Optimized scheduler manager for Gunicorn single-worker configuration, eliminates multi-worker conflicts |
| **simple_gunicorn_config.py** | Production WSGI Config | Main Class: DirectScheduler, Key Methods:  | Single-worker Gunicorn configuration optimized for scheduler stability and production reliability |


## Template Files

| File | Purpose | Description |
|------|---------|-------------|
| **templates/index.html** | Main Search Interface | Advanced database search with multi-criteria filtering, pagination, and CSV export |
| **templates/maintenance.html** | Database Management | Backup creation, cleanup tools, health monitoring, and statistics |
| **templates/scheduler.html** | Scheduler Administration | Job management with cron expressions, credential handling, and status monitoring |

## Data Storage

| File/Directory | Purpose | Description |
|---------------|---------|-------------|
| **device_lookup.db** | SQLite Optimization Cache | Fast device lookup database with composite indexes and LRU caching |
| **logs/** | Application Logs | Runtime logs, temporary collection files, and debug information |
| **backups/** | Database Backups | Native Python database backup storage with compression |


## Database Schema Optimization

### Core Tables with Composite Indexes
- **log_entries**: Primary storage with `(timestamp, switch_name)`, `(wwn, timestamp)` indexes
- **collection_runs**: Metadata tracking with UUID-based collection identification
- **scheduled_jobs**: Persistent scheduler configuration with encrypted credentials
- **switch_status**: Last successful collection tracking per switch

### Performance Features
- **Incremental Collection**: Date-based filtering to minimize duplicate processing
- **Batch Operations**: Optimized bulk insert operations for large datasets
- **Connection Pooling**: PostgreSQL connection management with pre-ping health checks
- **Query Optimization**: Index-aware query patterns for common search operations

## API Endpoints Structure

### Collection Operations
- `POST /api/collect/credentials` - Start collection with custom credentials
- `GET /api/collection/status` - Real-time collection status with progress details
- `GET /api/collections` - Historical collection runs with metadata

### Database Management
- `GET /api/db/search` - Advanced search with multi-criteria filtering
- `GET /api/db/stats` - Database statistics and performance metrics
- `GET /api/export-csv` - Streaming CSV export of search results

### Scheduler Administration
- `GET /api/scheduler/status` - Scheduler health and active job monitoring
- `POST /api/scheduler/jobs` - Create scheduled jobs with cron expressions
- `DELETE /api/scheduler/jobs/<id>` - Remove specific scheduled jobs

### Maintenance Operations
- `POST /api/db/backup` - Native database backup with compression
- `POST /api/db/collections/cleanup` - Clean up stuck collection processes
- `GET /api/device-lookup/stats` - Device lookup optimization statistics

  ## 🔄 Relazioni tra Componenti

### **Flusso Raccolta Dati**
```
main.py (API endpoint)
    ↓
final_working_collector.py (orchestrazione)
    ↓
simple_switch_collector.py (SSH + parsing)
    ↓
device_lookup_optimized.py (enrichment)
    ↓
models.py (persistenza)
```

### **Flusso Scheduler**
```
main.py (setup jobs)
    ↓
production_scheduler_config.py (coordinator)
    ↓
APScheduler (execution)
    ↓
main.py (scheduled_collection_job)
```

### **Flusso Configurazione**
```
gunicorn_config.py (WSGI setup)
    ↓
main.py (application init)
    ↓
config.py (load settings)
    ↓
models.py (database config)
```
