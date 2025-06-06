# Switch Log Analyzer - Project Structure

## Active Files Documentation

| File | Purpose | Classes/Functions | Description |
|------|---------|-------------------|-------------|
| **main.py** | Main Flask Application | `MockScheduler`, `cleanup_temporary_log_files()`, `create_native_backup()`, `scheduled_backup_job()`, `scheduled_collection_job()`, `setup_scheduled_jobs()`, `verify_scheduler_health()`, `create_tables()`, multiple route handlers | Core web application with scheduler management, database operations, and API endpoints |
| **models.py** | Database Models | `LogEntry`, `CollectionRun`, `AliasMapping`, `SwitchStatus`, `AppConfig`, `ScheduledJob` | PostgreSQL database models with optimized indexes for log storage and management |
| **production_scheduler_config.py** | Production Scheduler | `ProductionSchedulerManager` | File-based worker coordination for Gunicorn multi-worker scheduler management |
| **final_working_collector.py** | Data Collection System | `get_thread_db_session()`, `process_single_switch()`, `run_simple_collection()` | Parallel 4-switch log collection with PostgreSQL integration |
| **device_lookup_optimized.py** | Device Lookup Optimization | `DeviceLookupOptimized`, `extract_slot_port_from_entry()`, `lookup_alias_and_node_symbol()`, `refresh_device_port_data()` | SQLite-indexed device lookup with LRU cache and NPIV intelligence |
| **scheduler_daemon.py** | Standalone Scheduler Daemon | `SchedulerDaemon` | External scheduler process for production deployment |
| **config.py** | Application Configuration | `Config`, `Config.load_switches()` | Environment-based configuration management |
| **gunicorn_config.py** | Gunicorn Production Config | Various configuration functions | Production WSGI server configuration with security enhancements |

## Template Files

| File | Purpose | Description |
|------|---------|-------------|
| **templates/index.html** | Main Search Interface | Database search with filtering, pagination, and enhanced UI |
| **templates/maintenance.html** | Database Management | Backup/restore, cleanup tools, health monitoring |
| **templates/scheduler.html** | Scheduler Administration | Job management, status monitoring, scheduling interface |

## Configuration & Deployment

| File | Purpose | Description |
|------|---------|-------------|
| **switches.conf** | Switch Configuration | List of network switches for data collection |
| **deploy_production.sh** | Production Deployment | Automated deployment script with Gunicorn |
| **scheduler_service.sh** | Scheduler Service | Systemd service configuration for scheduler daemon |
| **start_daemon.sh** | Daemon Startup | Standalone scheduler daemon startup script |
| **systemd_service.sh** | System Service | Systemd service installation script |
| **pyproject.toml** | Python Dependencies | Package management and project metadata |

## Data & Logs

| Directory/File | Purpose | Description |
|---------------|---------|-------------|
| **device_lookup.db** | SQLite Cache | Optimized device lookup database with indexes |
| **logs/** | Application Logs | Runtime logs and temporary collection files |
| **backups/** | Database Backups | Native Python database backup storage |

## Key Features by Component

### Main Application (main.py)
- Multi-page Flask web interface
- PostgreSQL database integration
- Scheduler management with production safety
- Real-time collection status monitoring
- Native backup system without external dependencies
- API endpoints for all operations

### Database Models (models.py)
- Optimized PostgreSQL schema with composite indexes
- Collection run tracking and metadata
- Scheduled job persistence
- Switch status monitoring
- Alias mapping system

### Production Scheduler (production_scheduler_config.py)
- File-based worker coordination for Gunicorn
- Prevents scheduler conflicts in multi-worker environments
- Automatic worker takeover and cleanup
- Production-ready error handling

### Data Collection (final_working_collector.py)
- Parallel processing of 4 switches simultaneously
- Thread-safe database operations
- Comprehensive error handling and logging
- Integration with device lookup optimization

### Device Lookup (device_lookup_optimized.py)
- SQLite indexing for fast alias/node symbol lookups
- LRU caching for performance optimization
- NPIV intelligence for virtual/physical port mapping
- Memory-mapped JSON processing for large datasets

## Architecture Summary

The Switch Log Analyzer is a production-ready PostgreSQL-based system that:

1. **Collects** network switch logs via SSH using parallel processing
2. **Stores** data in optimized PostgreSQL database with comprehensive indexing
3. **Analyzes** logs with fast device lookup and alias mapping
4. **Schedules** automated collections using production-safe scheduler
5. **Provides** web interface for search, maintenance, and administration
6. **Deploys** with Gunicorn for production environments
7. **Backs up** data using native Python without external dependencies

All components are designed for production use with proper error handling, logging, and multi-worker safety.
