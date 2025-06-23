# Switch Log Analyzer - Project Structure

## 🔧 Main Components

### Core Files

| File | function | Description |
|------|----------|-------------|
| `main.py` | **Controller Principale** | Flask app with API REST, scheduler background and route management |
| `models.py` | **Database Schema** | Models SQLAlchemy for PostgreSQL with optimied index |
| `config.py` | **Configurazione** | Essetial Settings essenziali and loading switch list |

### Collection Engine

| File | function | Description |
|------|----------|-------------|
| `simple_switch_collector.py` | **Main Process** | SSH single connection, parsing log, timestamp management |
| `final_working_collector.py` | **Parallel Orchestrator** | Coordination of 4-8 simultaneous workers, database management |
| `device_lookup_optimized.py` | **Lookup devices** | SQLite cache + LRU, advanced NPIV logic |

### Configuration

| File | function | Description |
|------|----------|-------------|
| `switches.conf` | **Lista Switch** | Switch configuration in the format `site:hostname:generation` |
| `.env` | **Environment** | Database credentials and environment variables |


## Files Documentation

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

