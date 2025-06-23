#!/usr/bin/env python3
"""
Network Switch Log Analyzer Web Application - FINAL CLEAN VERSION
Analyzes WWN device logs across multiple switches and contexts
"""

import os
import json
import logging
import threading
import uuid
import glob
import time
from datetime import datetime, timedelta
from flask import Flask, render_template, request, jsonify, send_file
from simple_switch_collector import SimpleLogCollector
from config import Config
import tempfile
import csv
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
import atexit
import signal
import sys
from models import db, LogEntry, CollectionRun, AliasMapping, SwitchStatus, AppConfig, ScheduledJob
from final_working_collector import run_simple_collection as run_clean_collection
from device_lookup_optimized import device_lookup

# Load environment variables from .env file
from dotenv import load_dotenv
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('logs/app.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Create Flask app
app = Flask(__name__)
app.config.from_object(Config)

# Database configuration with optimized connection pooling
app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv('DATABASE_URL', 'postgresql://localhost/switch_analyzer')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
    'pool_size': 10,
    'pool_recycle': 300,
    'pool_pre_ping': True,
    'pool_timeout': 30,
    'max_overflow': 20
}

# Initialize database
db.init_app(app)

# Import scheduler configuration
from scheduler_config import SchedulerConfig, PREDEFINED_SCHEDULES, JOB_PRIORITIES

# Global scheduler with production-ready configuration
# In production with Gunicorn, scheduler runs separately
DISABLE_INTERNAL_SCHEDULER = SchedulerConfig.DISABLE_INTERNAL_SCHEDULER

if DISABLE_INTERNAL_SCHEDULER:
    # Mock scheduler for production when using external scheduler daemon
    class MockScheduler:
        @property
        def is_scheduler_worker(self): return True
        @property
        def scheduler(self): return None
        @property
        def running(self): return False
        def init_scheduler(self): pass
        def start(self): pass
        def shutdown(self): pass
        def add_job(self, *args, **kwargs): return None
        def remove_job(self, job_id): return False
        def get_job(self, job_id): return None
        def get_jobs(self): return []
        def remove_all_jobs(self): return False
        def pause_job(self, job_id): return False
        def resume_job(self, job_id): return False
        @property
        def running(self): return False
    
    scheduler = MockScheduler()
    logger.info("📅 SCHEDULER: Using external scheduler daemon (internal scheduler disabled)")
else:
    from simple_direct_scheduler import DirectScheduler
    scheduler = DirectScheduler()

# Global emergency scheduler for auto-failover
emergency_scheduler = None

# Global shutdown flag
shutdown_requested = False

def signal_handler(signum, frame):
    """Handle SIGTERM and SIGINT for graceful shutdown"""
    global shutdown_requested
    if shutdown_requested:
        return
    
    shutdown_requested = True
    signal_name = 'SIGTERM' if signum == signal.SIGTERM else 'SIGINT'
    logger.info(f"Received {signal_name}, initiating graceful shutdown...")
    
    try:
        # Shutdown scheduler
        if scheduler and hasattr(scheduler, 'shutdown'):
            logger.info("Shutting down scheduler...")
            scheduler.shutdown()
            logger.info("Scheduler shutdown complete")
        
        # Close database connections safely
        try:
            with app.app_context():
                if 'db' in globals():
                    logger.info("Closing database connections...")
                    db.session.close()
                    db.engine.dispose()
                    logger.info("Database connections closed")
        except Exception as db_error:
            logger.error(f"Error closing database connections: {db_error}")
            
        # Clean up lock files
        lock_files = ['logs/collection.lock', 'logs/backup.lock', '/tmp/scheduler_worker.lock']
        for lock_file in lock_files:
            try:
                if os.path.exists(lock_file):
                    os.remove(lock_file)
                    logger.info(f"Removed lock file: {lock_file}")
            except Exception as e:
                logger.warning(f"Could not remove lock file {lock_file}: {e}")
        
        logger.info("Graceful shutdown complete")
        
    except Exception as e:
        logger.error(f"Error during shutdown: {e}")
    
    # Exit cleanly
    sys.exit(0)

# Register signal handlers
signal.signal(signal.SIGTERM, signal_handler)
signal.signal(signal.SIGINT, signal_handler)

def cleanup_temporary_log_files():
    """Clean up temporary log files in logs directory"""
    try:
        logs_dir = 'logs'
        if not os.path.exists(logs_dir):
            return
        
        # Define patterns for temporary files to clean up (only safe patterns)
        temp_patterns = [
            'aliases_test_*.txt',        # Test alias files
            'simple_collection_test*.json',  # Test collection files
            'scheduler_config*.json',    # Temporary scheduler configs
            '*_temp.log',               # Explicitly temporary logs
            '*_debug.log',              # Debug logs
            'collection_*.tmp',         # Collection temporary files
            'context_set_*.json',       # Context collection output files
            'aliases_*.txt',            # Alias files from collections
            'simple_collection_*.json'  # Collection result files
        ]
        
        # Protected files that should NEVER be deleted
        protected_files = [
            'app.log',
            'main.log', 
            'error.log',
            'access.log',
            'production.log'
        ]
        
        cleaned_files = []
        for pattern in temp_patterns:
            temp_files = glob.glob(os.path.join(logs_dir, pattern))
            for temp_file in temp_files:
                try:
                    # Check if file is in protected list
                    filename = os.path.basename(temp_file)
                    if filename not in protected_files and not any(filename.endswith(pf) for pf in protected_files):
                        # Additional safety check: only delete files older than 1 hour
                        file_age = time.time() - os.path.getmtime(temp_file)
                        if file_age > 3600:  # 1 hour = 3600 seconds
                            os.remove(temp_file)
                            cleaned_files.append(filename)
                        else:
                            logger.debug(f"Skipping recent file {filename} (age: {file_age/60:.1f} minutes)")
                except OSError as e:
                    logger.warning(f"Failed to remove temporary file {temp_file}: {e}")
        
        if cleaned_files:
            logger.info(f"Cleaned up {len(cleaned_files)} temporary log files: {', '.join(cleaned_files)}")
        else:
            logger.debug("No temporary log files to clean up")
            
    except Exception as e:
        logger.error(f"Error during log cleanup: {e}")

def create_native_backup():
    """Create backup using native Python without external tools"""
    try:
        backup_dir = 'backups'
        os.makedirs(backup_dir, exist_ok=True)
        
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        backup_filename = f'switch_analyzer_backup_{timestamp}.json'
        backup_path = os.path.join(backup_dir, backup_filename)
        
        # Export data using SQLAlchemy
        backup_data = {
            'timestamp': timestamp,
            'log_entries': [],
            'collection_runs': [],
            'scheduled_jobs': [],
            'switch_status': [],
            'alias_mappings': []
        }
        
        # Export log entries (limit to recent entries to avoid huge files)
        recent_entries = LogEntry.query.order_by(LogEntry.timestamp.desc()).limit(50000).all()
        backup_data['log_entries'] = [entry.to_dict() for entry in recent_entries]
        
        # Export collection runs
        collections = CollectionRun.query.all()
        backup_data['collection_runs'] = [collection.to_dict() for collection in collections]
        
        # Export scheduled jobs
        jobs = ScheduledJob.query.all()
        backup_data['scheduled_jobs'] = [job.to_dict() for job in jobs]
        
        # Export switch status
        switches = SwitchStatus.query.all()
        backup_data['switch_status'] = [switch.to_dict() for switch in switches]
        
        # Export alias mappings
        aliases = AliasMapping.query.all()
        backup_data['alias_mappings'] = [alias.to_dict() for alias in aliases]
        
        # Write to file with compression
        import gzip
        import json
        
        with gzip.open(backup_path + '.gz', 'wt', encoding='utf-8') as f:
            json.dump(backup_data, f, indent=2, default=str)
        
        # Get file size
        stat = os.stat(backup_path + '.gz')
        logger.info(f"Native backup completed: {backup_filename}.gz ({stat.st_size} bytes)")
        logger.info(f"Backed up {len(backup_data['log_entries'])} log entries")
        
        return backup_path + '.gz'
        
    except Exception as e:
        logger.error(f"Native backup failed: {str(e)}")
        return None

def scheduled_backup_job():
    """Execute a scheduled backup using native method with lock protection"""
    backup_lock_file = 'logs/backup.lock'
    
    try:
        with app.app_context():
            # Check for existing lock file to prevent multiple simultaneous backups
            if os.path.exists(backup_lock_file):
                # Check if lock is stale (older than 10 minutes)
                lock_age = time.time() - os.path.getmtime(backup_lock_file)
                if lock_age < 600:  # 10 minutes
                    logger.warning(f"Scheduled backup skipped - already running (lock age: {lock_age/60:.1f} minutes)")
                    return
                else:
                    logger.info("Removing stale backup lock file")
                    os.remove(backup_lock_file)
            
            # Create lock file
            os.makedirs('logs', exist_ok=True)
            with open(backup_lock_file, 'w') as f:
                f.write(f"{os.getpid()}\n{time.time()}\n")
            
            logger.info("Scheduled backup lock acquired")
            
            try:
                logger.info("Starting scheduled backup...")
                
                # Try native backup first
                backup_path = create_native_backup()
                
                if backup_path:
                    logger.info("Scheduled backup completed successfully")
                    # Clean up temporary log files after successful backup
                    cleanup_temporary_log_files()
                else:
                    logger.error("Scheduled backup failed")
                    
            finally:
                # Always remove lock file
                try:
                    if os.path.exists(backup_lock_file):
                        os.remove(backup_lock_file)
                        logger.info("Scheduled backup lock released")
                except Exception as e:
                    logger.warning(f"Failed to remove backup lock: {e}")
                
    except Exception as e:
        logger.error(f"Scheduled backup job failed: {str(e)}")
        # Ensure lock is cleaned up on error
        try:
            if os.path.exists(backup_lock_file):
                os.remove(backup_lock_file)
        except:
            pass

def scheduled_collection_job(username=None, password=None):
    """Execute a scheduled collection using clean system with database lock protection"""
    try:
        with app.app_context():
            # Use database lock to prevent multiple simultaneous collections across all workers
            from sqlalchemy import text
            
            # Check if a collection is already running using database lock
            try:
                result = db.session.execute(text(
                    "SELECT pg_try_advisory_lock(12345) as acquired"
                )).fetchone()
                
                if not result.acquired:
                    logger.warning(f"Scheduled collection skipped - already running in another process (PID: {os.getpid()})")
                    return
                
                logger.info(f"🔒 DATABASE LOCK ACQUIRED: Scheduled collection starting (PID: {os.getpid()})")
                
                try:
                    # Use provided credentials if available, otherwise fall back to environment
                    if not username or not password:
                        username = os.getenv('SWITCH_USERNAME', '')
                        password = os.getenv('SWITCH_PASSWORD', '')

                    if not username or not password:
                        logger.error("Scheduled collection failed: No credentials configured")
                        return

                    logger.info(f"Starting scheduled collection with PID {os.getpid()}")
                    result = run_clean_collection(username, password)

                    if result['success']:
                        logger.info(f"Scheduled collection completed: {result['new_entries']} new entries")
                        # Clean up temporary log files after successful scheduled collection
                        cleanup_temporary_log_files()
                    else:
                        logger.error(f"Scheduled collection failed: {result.get('error', 'Unknown error')}")
                        
                finally:
                    # Always release database lock
                    try:
                        db.session.execute(text("SELECT pg_advisory_unlock(12345)"))
                        db.session.commit()
                        logger.info(f"Database lock released (PID: {os.getpid()})")
                    except Exception as e:
                        logger.warning(f"Failed to release database lock: {e}")
                        
            except Exception as e:
                logger.error(f"Database lock operation failed: {e}")
                return

    except Exception as e:
        logger.error(f"Scheduled collection error: {str(e)}")
        # Try to release lock on error
        try:
            with app.app_context():
                db.session.execute(text("SELECT pg_advisory_unlock(12345)"))
                db.session.commit()
        except:
            pass

def monitor_and_sync_jobs():
    """Simple job sync - only on scheduler worker"""
    try:
        with app.app_context():
            # Only run on scheduler worker
            if not scheduler or not scheduler.is_scheduler_worker or not scheduler.running:
                return
                
            # Get missing jobs
            scheduler_jobs = scheduler.get_jobs()
            db_jobs = ScheduledJob.query.filter_by(enabled=True).all()
            
            scheduler_ids = {job.id for job in scheduler_jobs}
            missing_jobs = [job for job in db_jobs if job.id not in scheduler_ids]
            
            # Add missing jobs quietly
            for job in missing_jobs:
                try:
                    trigger = CronTrigger.from_crontab(job.cron_expression)
                    if 'backup' in job.name.lower():
                        scheduler.add_job(
                            id=job.id,
                            name=job.name,
                            func=scheduled_backup_job,
                            trigger=trigger,
                            replace_existing=True,
                            max_instances=1
                        )
                    else:
                        # Decode password
                        import base64
                        try:
                            password = base64.b64decode(job.password.encode()).decode()
                        except:
                            password = job.password
                            
                        scheduler.add_job(
                            id=job.id,
                            name=job.name,
                            func=scheduled_collection_job,
                            trigger=trigger,
                            args=[job.username, password],
                            replace_existing=True,
                            max_instances=1
                        )
                except Exception as e:
                    logger.error(f"Failed to sync job {job.name}: {e}")
                    
    except Exception as e:
        logger.error(f"Job sync error: {e}")

def setup_scheduled_jobs():
    """Simple job setup - only on scheduler worker"""
    try:
        with app.app_context():
            # Only proceed on scheduler worker
            if not scheduler or not scheduler.is_scheduler_worker:
                return
                
            # Load enabled jobs from database
            scheduled_jobs = ScheduledJob.query.filter_by(enabled=True).all()
            
            for job in scheduled_jobs:
                try:
                    trigger = CronTrigger.from_crontab(job.cron_expression)
                    
                    if 'backup' in job.name.lower():
                        scheduler.add_job(
                            id=job.id,
                            name=job.name,
                            func=scheduled_backup_job,
                            trigger=trigger,
                            replace_existing=True,
                            max_instances=1
                        )
                    else:
                        # Decode password
                        import base64
                        try:
                            password = base64.b64decode(job.password.encode()).decode()
                        except:
                            password = job.password
                            
                        scheduler.add_job(
                            id=job.id,
                            name=job.name,
                            func=scheduled_collection_job,
                            trigger=trigger,
                            args=[job.username, password],
                            replace_existing=True,
                            max_instances=1
                        )
                    
                    # Update next run time
                    scheduler_job = scheduler.get_job(job.id)
                    if scheduler_job and scheduler_job.next_run_time:
                        job.next_run = scheduler_job.next_run_time
                        db.session.commit()
                        
                except Exception as e:
                    logger.error(f"Failed to setup job {job.name}: {e}")
                    
    except Exception as e:
        logger.error(f"Failed to setup scheduled jobs: {e}")

def verify_scheduler_health():
    """Verify scheduler is running and jobs are loaded"""
    try:
        if not scheduler.running:
            logger.warning("📅 SCHEDULER: Not running - attempting restart")
            scheduler.start()
            setup_scheduled_jobs()
            return False
            
        jobs = scheduler.get_jobs()
        db_jobs = ScheduledJob.query.filter_by(enabled=True).count()
        
        if len(jobs) != db_jobs:
            logger.warning(f"📅 SCHEDULER: Job count mismatch - Scheduler: {len(jobs)}, Database: {db_jobs}")
            setup_scheduled_jobs()
            return False
            
        logger.info(f"📅 SCHEDULER: Healthy - {len(jobs)} jobs running")
        return True
        
    except Exception as e:
        logger.error(f"Scheduler health check failed: {e}")
        return False

def create_tables():
    """Create database tables on startup"""
    try:
        with app.app_context():
            db.create_all()
            logger.info("DATABASE: Tables initialized successfully")

            # Initialize device lookup optimization
            logger.info("Initializing device lookup optimization...")
            device_lookup.refresh_index()
            logger.info("Device lookup optimization ready")

            # Jobs will be loaded after scheduler initialization
    except Exception as e:
        logger.error(f"DATABASE: Failed to initialize - {str(e)}")

@app.route('/')
def index():
    """Main page - Database search interface"""
    return render_template('index.html')

@app.route('/database')
def database_interface():
    """Redirect to main page"""
    return render_template('index.html')

@app.route('/maintenance')
def database_maintenance():
    """Database maintenance interface"""
    return render_template('maintenance.html')

@app.route('/scheduler')
def scheduler_admin():
    """Scheduler administration page"""
    return render_template('scheduler.html')

# Scheduler API endpoints
@app.route('/api/scheduler/status')
def scheduler_status():
    """Get scheduler status and job information from database"""
    try:
        # Force scheduler initialization - DirectScheduler auto-starts on first use
        try:
            if hasattr(scheduler, 'init_and_start'):
                scheduler.init_and_start()
                logger.info("FORCE-START: DirectScheduler initialized")
        except Exception as e:
            logger.debug(f"Force start attempt: {e}")
        
        # Force load all jobs from database
        try:
            from apscheduler.triggers.cron import CronTrigger
            db_jobs = ScheduledJob.query.filter_by(enabled=True).all()
            current_jobs = len(scheduler.get_jobs())
            
            if current_jobs < len(db_jobs):
                logger.info(f"FORCE-LOAD: Found {len(db_jobs)} DB jobs, {current_jobs} scheduler jobs")
                
                for job in db_jobs:
                    try:
                        trigger = CronTrigger.from_crontab(job.cron_expression)
                        
                        if 'backup' in job.name.lower():
                            scheduler.add_job(
                                id=job.id,
                                name=job.name,
                                func=scheduled_backup_job,
                                trigger=trigger,
                                replace_existing=True,
                                max_instances=1
                            )
                            logger.info(f"FORCE-LOAD: Added backup {job.name}")
                        else:
                            # Decode password from base64 for security
                            import base64
                            try:
                                decoded_password = base64.b64decode(job.password).decode('utf-8')
                            except:
                                decoded_password = job.password  # Fallback if not base64
                            
                            scheduler.add_job(
                                id=job.id,
                                name=job.name,
                                func=scheduled_collection_job,
                                trigger=trigger,
                                args=[job.username, decoded_password],
                                replace_existing=True,
                                max_instances=1
                            )
                            logger.info(f"FORCE-LOAD: Added collection {job.name}")
                    except Exception as e:
                        logger.error(f"FORCE-LOAD failed for {job.name}: {e}")
        except Exception as e:
            logger.error(f"Force-load error: {e}")
            
        with app.app_context():
            running = scheduler.running
            
            # Get all jobs from database
            scheduled_jobs = ScheduledJob.query.all()
            jobs = []
            
            # Separate collection and backup jobs
            collection_jobs = [job for job in scheduled_jobs if 'backup' not in job.name.lower()]
            backup_jobs = [job for job in scheduled_jobs if 'backup' in job.name.lower()]
            
            # Get all active jobs from scheduler directly
            active_scheduler_jobs = {}
            try:
                for scheduler_job in scheduler.get_jobs():
                    active_scheduler_jobs[scheduler_job.id] = scheduler_job
            except Exception as e:
                logger.warning(f"Could not get active jobs: {e}")
            
            for job in scheduled_jobs:
                # Check if job exists in active scheduler jobs
                scheduler_job = active_scheduler_jobs.get(job.id)
                
                job_info = {
                    'id': job.id,
                    'name': job.name,
                    'next_run': scheduler_job.next_run_time.isoformat() if scheduler_job and scheduler_job.next_run_time else "Not scheduled",
                    'cron_expression': job.cron_expression,
                    'enabled': job.enabled,
                    'created_at': job.created_at.isoformat() if job.created_at else None,
                    'last_run': job.last_run.isoformat() if job.last_run else None,
                    'in_scheduler': scheduler_job is not None
                }
                jobs.append(job_info)
            
            # Prepare status for frontend
            collection_enabled = len(collection_jobs) > 0 and any(job.enabled for job in collection_jobs)
            backup_enabled = len(backup_jobs) > 0 and any(job.enabled for job in backup_jobs)
            
            # Get latest collection and backup info
            latest_collection = collection_jobs[0] if collection_jobs else None
            latest_backup = backup_jobs[0] if backup_jobs else None
            
            # Get next run times
            next_collection = None
            next_backup = None
            
            if latest_collection:
                try:
                    if scheduler and scheduler.running:
                        scheduler_job = scheduler.get_job(latest_collection.id)
                        if scheduler_job and hasattr(scheduler_job, 'next_run_time') and scheduler_job.next_run_time:
                            next_collection = scheduler_job.next_run_time.isoformat()
                except Exception as e:
                    logger.debug(f"Could not get next collection time: {e}")
                    
            if latest_backup:
                try:
                    if scheduler and scheduler.running:
                        scheduler_job = scheduler.get_job(latest_backup.id)
                        if scheduler_job and hasattr(scheduler_job, 'next_run_time') and scheduler_job.next_run_time:
                            next_backup = scheduler_job.next_run_time.isoformat()
                except Exception as e:
                    logger.debug(f"Could not get next backup time: {e}")
            
            return jsonify({
                'running': running,
                'job_count': len(jobs),
                'jobs': jobs,
                # Collection status
                'collection_enabled': collection_enabled,
                'last_collection': latest_collection.last_run.isoformat() if latest_collection and latest_collection.last_run else None,
                'next_collection': next_collection,
                'collection_schedule': latest_collection.cron_expression if latest_collection else None,
                # Backup status
                'backup_enabled': backup_enabled,
                'last_backup': latest_backup.last_run.isoformat() if latest_backup and latest_backup.last_run else None,
                'next_backup': next_backup,
                'backup_schedule': latest_backup.cron_expression if latest_backup else None
            })
        
    except Exception as e:
        logger.error(f"Failed to get scheduler status: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/scheduler/health')
def scheduler_health():
    """Check and repair scheduler health in production"""
    try:
        with app.app_context():
            health_status = verify_scheduler_health()
            
            scheduler_info = {
                'running': scheduler.running if scheduler else False,
                'job_count': len(scheduler.get_jobs()) if scheduler and scheduler.running else 0,
                'health_ok': health_status
            }
            
            if not health_status:
                # Attempt to repair
                try:
                    if not scheduler.running:
                        scheduler.start()
                        logger.info("📅 SCHEDULER: Restarted scheduler")
                    setup_scheduled_jobs()
                    scheduler_info['repair_attempted'] = True
                    scheduler_info['health_ok'] = verify_scheduler_health()
                    logger.info("📅 SCHEDULER: Health check repair completed")
                except Exception as repair_error:
                    scheduler_info['repair_error'] = str(repair_error)
                    logger.error(f"📅 SCHEDULER: Health repair failed: {repair_error}")
            
            return jsonify(scheduler_info)
            
    except Exception as e:
        logger.error(f"Scheduler health check failed: {str(e)}")
        return jsonify({'error': str(e), 'health_ok': False}), 500

@app.route('/api/scheduler/debug')
def scheduler_debug():
    """Debug scheduler status and jobs with multi-worker detection"""
    try:
        with app.app_context():
            debug_info = {
                'scheduler_running': scheduler.running if scheduler else False,
                'jobs_in_scheduler': [],
                'jobs_in_database': [],
                'current_time': datetime.now().isoformat(),
                'scheduler_type': type(scheduler).__name__,
                'worker_info': {
                    'process_id': os.getpid(),
                    'parent_pid': os.getppid()
                },
                'multi_worker_detection': {
                    'warnings': [],
                    'status': 'unknown'
                }
            }
            
            # Detect multi-worker configuration
            try:
                import psutil
                current_proc = psutil.Process(os.getpid())
                parent_proc = psutil.Process(os.getppid())
                
                # Check if parent is gunicorn and has multiple children
                if 'gunicorn' in parent_proc.name().lower():
                    children = parent_proc.children(recursive=False)
                    debug_info['worker_info']['gunicorn_workers'] = len(children)
                    debug_info['worker_info']['worker_pids'] = [child.pid for child in children]
                    
                    if len(children) > 1:
                        debug_info['multi_worker_detection']['warnings'].append(
                            f'Multi-worker detected: {len(children)} Gunicorn workers running'
                        )
                        debug_info['multi_worker_detection']['status'] = 'CONFLICT_RISK'
                    else:
                        debug_info['multi_worker_detection']['status'] = 'HEALTHY'
                        
            except Exception as e:
                debug_info['multi_worker_detection']['detection_error'] = str(e)
            
            # Get jobs from scheduler
            if scheduler and scheduler.running:
                scheduler_jobs = scheduler.get_jobs()
                for job in scheduler_jobs:
                    debug_info['jobs_in_scheduler'].append({
                        'id': job.id,
                        'name': job.name,
                        'next_run': job.next_run_time.isoformat() if job.next_run_time else None,
                        'trigger': str(job.trigger)
                    })
            
            # Get jobs from database
            db_jobs = ScheduledJob.query.all()
            for job in db_jobs:
                debug_info['jobs_in_database'].append({
                    'id': job.id,
                    'name': job.name,
                    'enabled': job.enabled,
                    'cron_expression': job.cron_expression,
                    'created_at': job.created_at.isoformat() if job.created_at else None
                })
            
            return jsonify(debug_info)
            
    except Exception as e:
        logger.error(f"Scheduler debug failed: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/scheduler/multiworker-fix')
def scheduler_multiworker_fix():
    """Provide instructions to fix multi-worker scheduler conflicts"""
    try:
        fix_instructions = {
            'problem': 'Multi-worker Gunicorn configuration causing scheduler conflicts',
            'symptoms': [
                'Jobs running multiple times',
                'Scheduler initializing in multiple workers',
                'Log entries showing different worker PIDs'
            ],
            'solution_steps': [
                {
                    'step': 1,
                    'action': 'Run the fix script',
                    'command': 'cd /opt/SCDB && ./fix_gunicorn_multiworker.sh'
                },
                {
                    'step': 2,
                    'action': 'Verify single worker configuration',
                    'command': 'grep "workers = 1" /opt/SCDB/gunicorn_config.py'
                },
                {
                    'step': 3,
                    'action': 'Check service is using correct config',
                    'command': 'grep "gunicorn_config.py" /etc/systemd/system/nsdevlog.service'
                },
                {
                    'step': 4,
                    'action': 'Monitor logs for single worker',
                    'command': 'journalctl -u nsdevlog.service | grep "Single worker mode"'
                }
            ],
            'verification': {
                'endpoint': '/api/scheduler/debug',
                'expected': 'multi_worker_detection.status should be HEALTHY',
                'log_pattern': 'Single worker mode - PID XXXX running scheduler'
            }
        }
        
        return jsonify(fix_instructions)
        
    except Exception as e:
        logger.error(f"Error generating fix instructions: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/scheduler/test-backup', methods=['POST'])
def test_backup_job():
    """Test backup job execution immediately"""
    try:
        with app.app_context():
            logger.info("Manual test backup triggered")
            result = create_native_backup()
            
            if result:
                return jsonify({
                    'success': True,
                    'message': 'Test backup completed successfully',
                    'backup_file': result
                })
            else:
                return jsonify({
                    'success': False,
                    'message': 'Test backup failed'
                }), 500
                
    except Exception as e:
        logger.error(f"Test backup failed: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/scheduler/jobs', methods=['POST'])
def add_scheduled_job():
    """Add a new scheduled collection job with database persistence"""
    try:
        with app.app_context():
            data = request.get_json()
            
            job_name = data.get('name', 'Scheduled Collection')
            cron_expression = data.get('cron')
            username = data.get('username')
            password = data.get('password')
            
            if not all([cron_expression, username, password]):
                return jsonify({'error': 'Missing required fields'}), 400
            
            # Parse cron expression
            try:
                trigger = CronTrigger.from_crontab(cron_expression)
            except ValueError as e:
                return jsonify({'error': f'Invalid cron expression: {str(e)}'}), 400
            
            # Generate unique job ID based on type
            job_type = data.get('type', 'collection')
            job_id = f"{job_type}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            
            # Handle backup job type differently
            if job_type == 'backup':
                # For backup jobs, remove any existing backup job first (only one allowed)
                existing_backup_jobs = ScheduledJob.query.filter(ScheduledJob.name.like('%Backup%')).all()
                for existing_job in existing_backup_jobs:
                    try:
                        scheduler.remove_job(existing_job.id)
                    except:
                        pass
                    db.session.delete(existing_job)
                
                db.session.commit()
                
                # Save new backup job to database
                scheduled_job = ScheduledJob(
                    id=job_id,
                    name=job_name,
                    cron_expression=cron_expression,
                    username=username,
                    password=password,
                    enabled=True
                )
                
                db.session.add(scheduled_job)
                db.session.commit()
                
                scheduler.add_job(
                    id=job_id,
                    name=job_name,
                    func=scheduled_backup_job,
                    trigger=trigger,
                    replace_existing=True
                )
                
                # Log job details for debugging
                added_job = scheduler.get_job(job_id)
                if added_job:
                    logger.info(f"Backup job added successfully - Next run: {added_job.next_run_time}")
                else:
                    logger.error(f"Failed to add backup job {job_id}")
            else:
                # Save collection job to database
                scheduled_job = ScheduledJob(
                    id=job_id,
                    name=job_name,
                    cron_expression=cron_expression,
                    username=username,
                    password=password,  # Store original password for now
                    enabled=True
                )
                
                db.session.add(scheduled_job)
                db.session.commit()
                
                # Encrypt password for collection jobs
                import base64
                encrypted_password = base64.b64encode(password.encode()).decode()
                
                # Update the database record with encrypted password
                scheduled_job.password = encrypted_password
                db.session.commit()
                
                # Multi-worker safe job addition strategy
                # In multi-worker environment, only save to database - scheduler worker will pick it up
                job_added_to_scheduler = False
                
                try:
                    # Check if we're in the scheduler worker
                    if hasattr(scheduler, 'is_scheduler_worker') and scheduler.is_scheduler_worker:
                        # We're in the scheduler worker, try to add directly
                        if scheduler and hasattr(scheduler, 'scheduler') and scheduler.scheduler:
                            scheduler.add_job(
                                id=job_id,
                                name=job_name,
                                func=scheduled_collection_job,
                                trigger=trigger,
                                kwargs={'username': username, 'password': password},
                                replace_existing=True,
                                max_instances=1,
                                coalesce=True,
                                misfire_grace_time=60
                            )
                            
                            # Verify job was added
                            import time
                            time.sleep(0.2)
                            added_job = scheduler.get_job(job_id)
                            if added_job:
                                job_added_to_scheduler = True
                                logger.info(f"Collection job added directly to scheduler - Next run: {added_job.next_run_time}")
                            else:
                                logger.warning(f"Job {job_id} not found in scheduler after direct addition")
                
                except Exception as e:
                    logger.warning(f"Direct scheduler addition failed: {str(e)}")
                
                if not job_added_to_scheduler:
                    # Job saved to database - use cleanup mechanism to sync with scheduler
                    logger.info(f"Job {job_id} saved to database - will be loaded by scheduler worker")
                    
                    # The cleanup endpoint will detect this job and add it to scheduler
                    # This works across worker boundaries since it checks database vs scheduler state
            
            logger.info(f"Added scheduled job: {job_name} ({cron_expression})")
            
            return jsonify({
                'success': True,
                'job_id': job_id,
                'message': f'Scheduled job "{job_name}" added successfully'
            })
        
    except Exception as e:
        logger.error(f"Failed to add scheduled job: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/scheduler/jobs/<job_id>', methods=['DELETE'])
def remove_scheduled_job(job_id):
    """Remove a scheduled job from both scheduler and database"""
    try:
        with app.app_context():
            # Remove from scheduler
            try:
                scheduler.remove_job(job_id)
            except:
                pass  # Job might not exist in scheduler
            
            # Remove from database
            scheduled_job = ScheduledJob.query.filter_by(id=job_id).first()
            if scheduled_job:
                db.session.delete(scheduled_job)
                db.session.commit()
                logger.info(f"Removed scheduled job: {job_id}")
                
                return jsonify({
                    'success': True,
                    'message': f'Job {job_id} removed successfully'
                })
            else:
                return jsonify({'error': 'Job not found'}), 404
        
    except Exception as e:
        logger.error(f"Failed to remove job {job_id}: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/scheduler/jobs/<job_id>/pause', methods=['POST'])
def pause_scheduled_job(job_id):
    """Pause a scheduled job"""
    try:
        scheduler.pause_job(job_id)
        logger.info(f"Paused scheduled job: {job_id}")
        
        return jsonify({
            'success': True,
            'message': f'Job {job_id} paused successfully'
        })
        
    except Exception as e:
        logger.error(f"Failed to pause job {job_id}: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/scheduler/jobs/<job_id>/resume', methods=['POST'])
def resume_scheduled_job(job_id):
    """Resume a paused job"""
    try:
        scheduler.resume_job(job_id)
        logger.info(f"Resumed scheduled job: {job_id}")
        
        return jsonify({
            'success': True,
            'message': f'Job {job_id} resumed successfully'
        })
        
    except Exception as e:
        logger.error(f"Failed to resume job {job_id}: {str(e)}")
        return jsonify({'error': str(e)}), 500



# SINGLE CLEAN COLLECTION ENDPOINT
@app.route('/api/db/collect', methods=['POST'])
def collect_data():
    """ONLY clean collection endpoint - replaces all others"""
    try:
        # Try to get credentials from request body first, then environment
        try:
            data = request.get_json() or {}
        except:
            data = {}

        username = data.get('username') or os.getenv('SWITCH_USERNAME', '')
        password = data.get('password') or os.getenv('SWITCH_PASSWORD', '')

        if not username or not password:
            return jsonify({
                'success': False,
                'error': 'Switch credentials not configured',
                'message': 'Please provide SSH credentials to start collection',
                'needs_credentials': True
            }), 400

        # Check for active collections
        thirty_minutes_ago = datetime.utcnow() - timedelta(minutes=30)
        active_collection = CollectionRun.query.filter(
            CollectionRun.status == 'running',
            CollectionRun.started_at > thirty_minutes_ago
        ).first()

        if active_collection:
            time_diff = datetime.utcnow() - active_collection.started_at
            minutes_ago = int(time_diff.total_seconds() / 60)
            return jsonify({
                'success': False,
                'error': f'Collection already in progress (started {minutes_ago} minutes ago). Please wait for completion.',
                'lock_info': {
                    'collection_id': active_collection.id,
                    'started_at': active_collection.started_at.strftime("%H:%M:%S"),
                    'minutes_ago': minutes_ago
                }
            }), 409

        def run_collection():
            try:
                with app.app_context():
                    lock_file = 'logs/collection.lock'

                    if os.path.exists(lock_file):
                        with open(lock_file, 'r') as f:
                            lock_data = json.loads(f.read())
                            lock_time = datetime.fromisoformat(lock_data['start_time'])
                            age_minutes = (datetime.now() - lock_time).total_seconds() / 60
                            if age_minutes < 30:
                                logger.warning("Collection already in progress")
                                return
                            else:
                                os.remove(lock_file)

                    os.makedirs('logs', exist_ok=True)
                    with open(lock_file, 'w') as f:
                        json.dump({
                            'start_time': datetime.now().isoformat(),
                            'status': 'running'
                        }, f)

                    try:
                        result = run_clean_collection(username, password)

                        if result['success']:
                            logger.info(f"Clean collection completed: {result['new_entries']} new entries from {result['switches_processed']} switches")
                            # Clean up temporary log files after successful collection
                            cleanup_temporary_log_files()
                        else:
                            logger.error(f"Clean collection failed: {result.get('error', 'Unknown error')}")

                    finally:
                        if os.path.exists(lock_file):
                            os.remove(lock_file)

            except Exception as e:
                logger.error(f"Fatal collection error: {str(e)}")
                lock_file = 'logs/collection.lock'
                if os.path.exists(lock_file):
                    os.remove(lock_file)

        collection_thread = threading.Thread(target=run_collection)
        collection_thread.daemon = True
        collection_thread.start()

        return jsonify({
            'success': True,
            'message': 'Clean collection started - only new entries will be added'
        })

    except Exception as e:
        logger.error(f"Failed to start collection: {str(e)}")
        return jsonify({'error': str(e)}), 500

# Database and search endpoints
@app.route('/api/db/search')
def search_database():
    """Enhanced search with date filtering, multi-switch selection, pagination, and sorting"""
    max_retries = 3
    retry_count = 0
    
    while retry_count < max_retries:
        try:
            with app.app_context():
                # Reconnect database if needed
                if retry_count > 0:
                    db.session.remove()
                    db.engine.dispose()
                
                wwn = request.args.get('wwn', '').strip()
                alias = request.args.get('alias', '').strip()
                node_symbol = request.args.get('node_symbol', '').strip()
                switches = request.args.get('switches', '').strip()
                event = request.args.get('event', '').strip()
                context = request.args.get('context', '').strip()
                date_from = request.args.get('date_from', '').strip()
                date_to = request.args.get('date_to', '').strip()
                
                # Pagination parameters
                page = int(request.args.get('page', 1))
                page_size = int(request.args.get('page_size', 100))
                
                # Handle export mode (page_size=0 means export all)
                export_mode = (page_size == 0)
                if not export_mode:
                    page_size = min(page_size, 1000)  # Cap at 1000 for normal pagination
                
                # Sorting parameters
                sort_column = request.args.get('sort_column', 'timestamp')
                sort_direction = request.args.get('sort_direction', 'desc')
                
                query = LogEntry.query
                
                # Apply filters
                if wwn:
                    query = query.filter(LogEntry.wwn.ilike(f'%{wwn}%'))
                
                if alias:
                    query = query.filter(LogEntry.alias.ilike(f'%{alias}%'))
                
                if node_symbol:
                    query = query.filter(LogEntry.node_symbol.ilike(f'%{node_symbol}%'))
                
                if switches:
                    switch_list = [s.strip() for s in switches.split(',') if s.strip()]
                    if switch_list:
                        query = query.filter(LogEntry.switch_name.in_(switch_list))
                
                if event:
                    query = query.filter(LogEntry.event_type.ilike(f'%{event}%'))
                
                if context:
                    query = query.filter(LogEntry.context == int(context))
                    
                # Date filtering
                if date_from:
                    from datetime import datetime
                    date_from_obj = datetime.strptime(date_from, '%Y-%m-%d')
                    query = query.filter(LogEntry.timestamp >= date_from_obj)
                    
                if date_to:
                    from datetime import datetime
                    date_to_obj = datetime.strptime(date_to, '%Y-%m-%d')
                    # Add 1 day to include the entire day
                    date_to_obj = date_to_obj.replace(hour=23, minute=59, second=59)
                    query = query.filter(LogEntry.timestamp <= date_to_obj)
                
                # Apply sorting
                sort_attr = getattr(LogEntry, sort_column, LogEntry.timestamp)
                if sort_direction and sort_direction.lower() == 'desc':
                    query = query.order_by(sort_attr.desc())
                else:
                    query = query.order_by(sort_attr.asc())
                
                # Get total count with simplified query for performance
                try:
                    total = query.count()
                except Exception:
                    # Fallback: use a simpler count query
                    total = db.session.query(db.func.count(LogEntry.id)).scalar() or 0
                
                # Apply pagination only if not in export mode
                if export_mode:
                    # Export mode: return all results without pagination
                    entries = query.all()
                    return jsonify({
                        'entries': [entry.to_dict() for entry in entries],
                        'total': total,
                        'page': 1,
                        'page_size': len(entries),
                        'total_pages': 1
                    })
                else:
                    # Normal pagination mode
                    offset = (page - 1) * page_size
                    entries = query.offset(offset).limit(page_size).all()
                    
                    return jsonify({
                        'entries': [entry.to_dict() for entry in entries],
                        'total': total,
                        'page': page,
                        'page_size': page_size,
                        'total_pages': (total + page_size - 1) // page_size if total > 0 else 0
                    })

        except Exception as e:
            retry_count += 1
            logger.warning(f"Database search attempt {retry_count} failed: {str(e)}")
            
            if retry_count >= max_retries:
                logger.error(f"Database search failed after {max_retries} retries: {str(e)}")
                return jsonify({'error': f'Database connection failed: {str(e)}'}), 500
            
            # Wait before retry
            import time
            time.sleep(0.5)
    
    return jsonify({'error': 'Database search failed after retries'}), 500

@app.route('/api/db/stats')
def database_stats():
    """Get database statistics"""
    try:
        with app.app_context():
            total_entries = LogEntry.query.count()
            total_collections = CollectionRun.query.count()
            total_aliases = AliasMapping.query.count()

            # Get active switches count from SwitchStatus table
            active_switches = SwitchStatus.query.filter_by(status='active').count()

            # Get database size
            from sqlalchemy import text
            db_size_result = db.session.execute(text("SELECT pg_size_pretty(pg_database_size(current_database()));"))
            db_size = db_size_result.scalar() or "Unknown"

            # Get table sizes
            table_size_result = db.session.execute(text("""
                SELECT
                    schemaname,
                    tablename,
                    pg_size_pretty(pg_total_relation_size(schemaname||'.'||tablename)) as size_pretty,
                    pg_total_relation_size(schemaname||'.'||tablename) as size_bytes
                FROM pg_tables
                WHERE schemaname = 'public'
                ORDER BY pg_total_relation_size(schemaname||'.'||tablename) DESC;
            """))
            table_sizes = [dict(row._mapping) for row in table_size_result]

            switch_counts = db.session.query(
                LogEntry.switch_name,
                db.func.count(LogEntry.id).label('count')
            ).group_by(LogEntry.switch_name).all()

            context_counts = db.session.query(
                LogEntry.context,
                db.func.count(LogEntry.id).label('count')
            ).group_by(LogEntry.context).all()

            event_counts = db.session.query(
                LogEntry.event_type,
                db.func.count(LogEntry.id).label('count')
            ).group_by(LogEntry.event_type).order_by(db.func.count(LogEntry.id).desc()).limit(10).all()

            return jsonify({
                'total_entries': total_entries,
                'total_collections': total_collections,
                'total_aliases': total_aliases,
                'active_switches': active_switches,
                'database_size': db_size,
                'table_sizes': table_sizes,
                'switches': [{'name': s[0], 'count': s[1]} for s in switch_counts],
                'contexts': [{'context': c[0], 'count': c[1]} for c in context_counts],
                'top_events': [{'event': e[0], 'count': e[1]} for e in event_counts]
            })

    except Exception as e:
        logger.error(f"Failed to get database stats: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/collection/status')
def get_collection_status():
    """Check if a collection is currently in progress"""
    try:
        with app.app_context():
            lock_file = 'logs/collection.lock'

            # Check database for running collections
            thirty_minutes_ago = datetime.utcnow() - timedelta(minutes=30)
            active_collection = CollectionRun.query.filter(
                CollectionRun.status == 'running',
                CollectionRun.started_at > thirty_minutes_ago
            ).first()

            # Check file lock as backup
            file_lock_active = os.path.exists(lock_file)

            is_running = active_collection is not None or file_lock_active

            status_info = {
                'is_running': is_running,
                'database_lock': active_collection is not None,
                'file_lock': file_lock_active
            }

            if active_collection:
                time_diff = datetime.utcnow() - active_collection.started_at
                status_info['collection_id'] = active_collection.id
                status_info['started_at'] = active_collection.started_at.isoformat()
                status_info['duration_minutes'] = int(time_diff.total_seconds() // 60)

            return jsonify(status_info)

    except Exception as e:
        logger.error(f"Failed to get collection status: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/db/collections')
def list_collections():
    """List recent collection runs"""
    try:
        with app.app_context():
            collections = CollectionRun.query.order_by(
                CollectionRun.started_at.desc()
            ).limit(20).all()

            return jsonify({
                'collections': [c.to_dict() for c in collections]
            })

    except Exception as e:
        logger.error(f"Failed to list collections: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/db/health')
def database_health():
    """Get database health information"""
    try:
        with app.app_context():
            # Test database connectivity
            total_entries = LogEntry.query.count()
            total_collections = CollectionRun.query.count()

            # Get recent activity
            recent_collection = CollectionRun.query.order_by(
                CollectionRun.started_at.desc()
            ).first()

            last_activity = None
            if recent_collection:
                last_activity = recent_collection.started_at.isoformat()

            return jsonify({
                'status': 'healthy',
                'total_entries': total_entries,
                'total_collections': total_collections,
                'last_activity': last_activity,
                'database_connected': True
            })

    except Exception as e:
        logger.error(f"Database health check failed: {str(e)}")
        return jsonify({
            'status': 'unhealthy',
            'error': str(e),
            'database_connected': False
        }), 500

@app.route('/api/db/backups')
def list_backups():
    """List available backup files"""
    try:
        backup_dir = 'backups'
        if not os.path.exists(backup_dir):
            os.makedirs(backup_dir)

        backups = []
        for filename in os.listdir(backup_dir):
            if filename.endswith('.sql') or filename.endswith('.sql.gz') or filename.endswith('.json.gz'):
                filepath = os.path.join(backup_dir, filename)
                stat = os.stat(filepath)
                backups.append({
                    'filename': filename,
                    'size': stat.st_size,
                    'created': datetime.fromtimestamp(stat.st_ctime).isoformat()
                })

        backups.sort(key=lambda x: x['created'], reverse=True)

        return jsonify({
            'backups': backups
        })

    except Exception as e:
        logger.error(f"Failed to list backups: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/db/backup', methods=['POST'])
def create_backup():
    """Create database backup using native method"""
    try:
        backup_path = create_native_backup()
        
        if backup_path:
            backup_filename = os.path.basename(backup_path)
            stat = os.stat(backup_path)
            return jsonify({
                'success': True,
                'filename': backup_filename,
                'size': stat.st_size,
                'path': backup_path
            })
        else:
            return jsonify({
                'error': 'Backup failed - check logs for details'
            }), 500

    except Exception as e:
        logger.error(f"Failed to create backup: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/db/backup/<filename>', methods=['DELETE'])
def delete_backup(filename):
    """Delete a backup file"""
    try:
        backup_dir = 'backups'
        if not os.path.exists(backup_dir):
            return jsonify({'error': 'Backup directory not found'}), 404

        filepath = os.path.join(backup_dir, filename)

        # Security check - ensure filename doesn't contain path traversal
        if '..' in filename or '/' in filename or '\\' in filename:
            return jsonify({'error': 'Invalid filename'}), 400

        if not os.path.exists(filepath):
            return jsonify({'error': 'Backup file not found'}), 404

        if not (filename.endswith('.sql') or filename.endswith('.sql.gz') or filename.endswith('.json.gz')):
            return jsonify({'error': 'Only backup files can be deleted'}), 400

        os.remove(filepath)
        logger.info(f"Deleted backup file: {filename}")

        return jsonify({
            'success': True,
            'message': f'Backup {filename} deleted successfully'
        })

    except Exception as e:
        logger.error(f"Failed to delete backup {filename}: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/db/collections/cleanup', methods=['POST'])
def cleanup_stuck_collections():
    """Clean up collections that are stuck in 'running' status"""
    try:
        stuck_collections = CollectionRun.query.filter(
            CollectionRun.status == 'running'
        ).all()

        cleanup_count = 0
        for collection in stuck_collections:
            collection.status = 'failed'
            collection.error_message = 'Collection cleanup - marked as failed by manual cleanup'
            collection.completed_at = datetime.utcnow()
            cleanup_count += 1
            logger.info(f"Cleaned up stuck collection {collection.id}")

        # Also remove any old lock files
        lock_file = 'logs/collection.lock'
        if os.path.exists(lock_file):
            os.remove(lock_file)
            logger.info("Removed stale lock file")

        db.session.commit()

        return jsonify({
            'success': True,
            'message': f'Cleaned up {cleanup_count} stuck collections',
            'cleaned_count': cleanup_count
        })

    except Exception as e:
        logger.error(f"Failed to cleanup collections: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/collect-with-credentials', methods=['POST'])
def collect_with_credentials():
    """Start collection with user-provided credentials"""
    try:
        data = request.get_json()
        if not data:
            return jsonify({'error': 'Request body required'}), 400

        username = data.get('username', '').strip()
        password = data.get('password', '').strip()

        if not username or not password:
            return jsonify({'error': 'Username and password required'}), 400

        # Check for active collections
        thirty_minutes_ago = datetime.utcnow() - timedelta(minutes=30)
        active_collection = CollectionRun.query.filter(
            CollectionRun.status == 'running',
            CollectionRun.started_at > thirty_minutes_ago
        ).first()

        if active_collection:
            time_diff = datetime.utcnow() - active_collection.started_at
            minutes_ago = int(time_diff.total_seconds() / 60)
            return jsonify({
                'success': False,
                'error': f'Collection already in progress (started {minutes_ago} minutes ago). Please wait for completion.',
                'lock_info': {
                    'collection_id': active_collection.id,
                    'started_at': active_collection.started_at.strftime("%H:%M:%S"),
                    'minutes_ago': minutes_ago
                }
            }), 409

        def run_collection():
            try:
                with app.app_context():
                    lock_file = 'logs/collection.lock'

                    if os.path.exists(lock_file):
                        with open(lock_file, 'r') as f:
                            lock_data = json.loads(f.read())
                            lock_time = datetime.fromisoformat(lock_data['start_time'])
                            age_minutes = (datetime.now() - lock_time).total_seconds() / 60
                            if age_minutes < 30:
                                logger.warning("Collection already in progress")
                                return
                            else:
                                os.remove(lock_file)

                    os.makedirs('logs', exist_ok=True)
                    with open(lock_file, 'w') as f:
                        json.dump({
                            'start_time': datetime.now().isoformat(),
                            'status': 'running'
                        }, f)

                    try:
                        result = run_clean_collection(username, password)

                        if result['success']:
                            logger.info(f"Collection with user credentials completed: {result['new_entries']} new entries from {result['switches_processed']} switches")
                            # Clean up temporary log files after successful collection with credentials
                            cleanup_temporary_log_files()
                        else:
                            logger.error(f"Collection with user credentials failed: {result.get('error', 'Unknown error')}")

                    finally:
                        if os.path.exists(lock_file):
                            os.remove(lock_file)

            except Exception as e:
                logger.error(f"Fatal collection error: {str(e)}")
                lock_file = 'logs/collection.lock'
                if os.path.exists(lock_file):
                    os.remove(lock_file)

        collection_thread = threading.Thread(target=run_collection)
        collection_thread.daemon = True
        collection_thread.start()

        return jsonify({
            'success': True,
            'message': 'Collection started with provided credentials - only new entries will be added'
        })

    except Exception as e:
        logger.error(f"Failed to start collection with credentials: {str(e)}")
        return jsonify({'error': str(e)}), 500



@app.route('/api/db/collect', methods=['POST'])
def collect_data_maintenance():
    """Collection endpoint for maintenance page"""
    try:
        # Check if collection is already running
        running_collection = CollectionRun.query.filter_by(status='running').first()
        if running_collection:
            return jsonify({
                'success': False,
                'error': 'Another collection is already in progress'
            }), 409

        # Check if we have default credentials
        username = Config.DEFAULT_USERNAME
        password = Config.DEFAULT_PASSWORD

        if not username or not password:
            return jsonify({
                'needs_credentials': True,
                'message': 'Credentials required for collection'
            })

        def run_collection():
            try:
                logger.info("Starting maintenance collection")
                result = run_clean_collection(username, password)
                logger.info(f"Collection completed: {result}")
                if result.get('success'):
                    # Clean up temporary log files after successful maintenance collection
                    cleanup_temporary_log_files()
                return result
            except Exception as e:
                logger.error(f"Collection failed: {e}")
                return {'success': False, 'error': str(e)}

        # Start collection in background thread
        import threading
        thread = threading.Thread(target=run_collection)
        thread.daemon = True
        thread.start()

        return jsonify({
            'success': True,
            'message': 'Collection started in background'
        })

    except Exception as e:
        logger.error(f"Failed to start collection: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500



@app.route('/api/device-lookup/stats')
def device_lookup_stats():
    """Get device lookup optimization statistics"""
    try:
        stats = device_lookup.get_statistics()
        
        # Calcola hit rate percentuale
        cache_info = stats.get('cache_info', {})
        hits = cache_info.get('hits', 0)
        misses = cache_info.get('misses', 0)
        total_requests = hits + misses
        hit_rate = (hits / total_requests * 100) if total_requests > 0 else 0
        
        # Aggiungi metriche calcolate
        stats['hit_rate_percent'] = round(hit_rate, 1)
        stats['total_cache_requests'] = total_requests
        
        return jsonify(stats)
    except Exception as e:
        logger.error(f"Failed to get device lookup stats: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/device-lookup/cache-debug')
def device_lookup_cache_debug():
    """Debug endpoint per monitorare cache performance dettagliata"""
    try:
        stats = device_lookup.get_statistics()
        cache_info = stats.get('cache_info', {})
        
        debug_info = {
            'cache_status': {
                'hits': cache_info.get('hits', 0),
                'misses': cache_info.get('misses', 0), 
                'current_size': cache_info.get('currsize', 0),
                'max_size': cache_info.get('maxsize', 10000)
            },
            'database_status': {
                'total_devices': stats.get('total_devices', 0),
                'devices_with_alias': stats.get('devices_with_alias', 0),
                'npiv_devices': stats.get('npiv_devices', 0),
                'unique_switches': stats.get('unique_switches', 0)
            },
            'performance_metrics': {
                'hit_rate_percent': round((cache_info.get('hits', 0) / (cache_info.get('hits', 0) + cache_info.get('misses', 0)) * 100) if (cache_info.get('hits', 0) + cache_info.get('misses', 0)) > 0 else 0, 2),
                'cache_efficiency': 'excellent' if cache_info.get('hits', 0) > cache_info.get('misses', 0) else 'warming_up' if cache_info.get('misses', 0) > 0 else 'unused'
            }
        }
        
        return jsonify(debug_info)
        
    except Exception as e:
        logger.error(f"Error in cache debug endpoint: {e}")
        return jsonify({'error': str(e)}), 500

# Missing routes that are called by templates
@app.route('/api/export-csv')
def export_csv():
    """Export search results to CSV"""
    try:
        # Get search parameters
        search_params = {
            'wwn': request.args.get('wwn', ''),
            'alias': request.args.get('alias', ''),
            'node_symbol': request.args.get('node_symbol', ''),
            'switch_name': request.args.get('switch_name', ''),
            'event_type': request.args.get('event_type', ''),
            'start_date': request.args.get('start_date', ''),
            'end_date': request.args.get('end_date', ''),
        }
        
        # Build query using same logic as search endpoint
        query = LogEntry.query
        
        if search_params['wwn']:
            query = query.filter(LogEntry.wwn.ilike(f"%{search_params['wwn']}%"))
        if search_params['alias']:
            query = query.filter(LogEntry.alias.ilike(f"%{search_params['alias']}%"))
        if search_params['node_symbol']:
            query = query.filter(LogEntry.node_symbol.ilike(f"%{search_params['node_symbol']}%"))
        if search_params['switch_name']:
            query = query.filter(LogEntry.switch_name.ilike(f"%{search_params['switch_name']}%"))
        if search_params['event_type']:
            query = query.filter(LogEntry.event_type.ilike(f"%{search_params['event_type']}%"))
        if search_params['start_date']:
            start_dt = datetime.fromisoformat(search_params['start_date'].replace('Z', '+00:00'))
            query = query.filter(LogEntry.timestamp >= start_dt)
        if search_params['end_date']:
            end_dt = datetime.fromisoformat(search_params['end_date'].replace('Z', '+00:00'))
            query = query.filter(LogEntry.timestamp <= end_dt)
            
        entries = query.order_by(LogEntry.timestamp.desc()).all()
        
        # Create CSV content
        import io
        output = io.StringIO()
        writer = csv.writer(output)
        
        # Write header
        writer.writerow([
            'Timestamp', 'Switch', 'Context', 'Event Type', 'WWN', 
            'Port Info', 'Alias', 'Node Symbol', 'Raw Line'
        ])
        
        # Write data
        for entry in entries:
            writer.writerow([
                entry.timestamp.isoformat(),
                entry.switch_name,
                entry.context,
                entry.event_type or '',
                entry.wwn or '',
                entry.port_info or '',
                entry.alias or '',
                entry.node_symbol or '',
                entry.raw_line
            ])
        
        # Create response
        response = app.response_class(
            output.getvalue(),
            mimetype='text/csv',
            headers={'Content-Disposition': 'attachment; filename=switch_logs_export.csv'}
        )
        return response
        
    except Exception as e:
        logger.error(f"Export failed: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/db/collections/force-cleanup', methods=['POST'])
def force_cleanup_collections():
    """Force cleanup of all stuck collections"""
    try:
        # Update all running collections to failed status
        stuck_collections = CollectionRun.query.filter_by(status='running').all()
        for collection in stuck_collections:
            collection.status = 'failed'
            collection.completed_at = datetime.utcnow()
            collection.error_message = 'Force cleaned up - was stuck in running status'
        
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': f'Force cleaned up {len(stuck_collections)} stuck collections'
        })
        
    except Exception as e:
        logger.error(f"Force cleanup failed: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/db/restore', methods=['POST'])
def restore_database():
    """Restore database from backup (placeholder - requires implementation)"""
    return jsonify({
        'error': 'Database restore functionality not yet implemented'
    }), 501

@app.route('/api/logs/cleanup', methods=['POST'])
def manual_log_cleanup():
    """Manually trigger cleanup of temporary log files"""
    try:
        cleanup_temporary_log_files()
        return jsonify({
            'success': True,
            'message': 'Temporary log files cleanup completed'
        })
    except Exception as e:
        logger.error(f"Manual log cleanup failed: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/maintenance/force-remove-job/<job_id>', methods=['DELETE'])
def force_remove_job(job_id):
    """Force remove a job from database even if not in scheduler"""
    try:
        with app.app_context():
            # Find job in database
            job = ScheduledJob.query.filter_by(id=job_id).first()
            if not job:
                return jsonify({'error': 'Job not found in database'}), 404
            
            # Remove from scheduler if present
            try:
                if scheduler and scheduler.running:
                    scheduler.remove_job(job_id)
                    logger.info(f"Removed job {job_id} from scheduler")
            except Exception as e:
                logger.warning(f"Could not remove job {job_id} from scheduler: {e}")
            
            # Remove from database
            db.session.delete(job)
            db.session.commit()
            logger.info(f"Force removed job {job_id} from database")
            
            return jsonify({
                'success': True,
                'message': f'Job {job_id} force removed successfully'
            })
            
    except Exception as e:
        logger.error(f"Force remove job failed: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/maintenance/cleanup-scheduler-jobs', methods=['POST'])
def cleanup_scheduler_jobs():
    """Clean up orphaned or duplicate scheduler jobs"""
    try:
        with app.app_context():
            # Force immediate sync of all jobs
            from apscheduler.schedulers.background import BackgroundScheduler
            
            # Get or create active scheduler
            active_scheduler = None
            if scheduler and scheduler.running:
                if hasattr(scheduler, 'scheduler') and scheduler.scheduler:
                    active_scheduler = scheduler.scheduler
                else:
                    active_scheduler = scheduler
            else:
                # Use global scheduler directly
                active_scheduler = scheduler
                logger.info(f"Using global scheduler on worker {os.getpid()}")
            
            if not active_scheduler:
                return jsonify({'error': 'No scheduler available'}), 500
            
            # Remove all existing jobs except sync monitor
            current_jobs = active_scheduler.get_jobs()
            for job in current_jobs:
                if job.id != 'job_sync_monitor':
                    active_scheduler.remove_job(job.id)
                    logger.info(f"Removed job: {job.id}")
            
            # Load all enabled jobs from database
            db_jobs = ScheduledJob.query.filter_by(enabled=True).all()
            jobs_added = 0
            
            for job in db_jobs:
                try:
                    from apscheduler.triggers.cron import CronTrigger
                    cron_parts = job.cron_expression.split()
                    if len(cron_parts) == 5:
                        minute, hour, day, month, day_of_week = cron_parts
                        trigger = CronTrigger(minute=minute, hour=hour, day=day, month=month, day_of_week=day_of_week)
                        
                        if 'backup' in job.name.lower():
                            active_scheduler.add_job(
                                id=job.id,
                                name=job.name,
                                func=scheduled_backup_job,
                                trigger=trigger,
                                replace_existing=True,
                                max_instances=1
                            )
                        else:
                            # Decode password from base64 for security
                            import base64
                            try:
                                decoded_password = base64.b64decode(job.password).decode('utf-8')
                            except:
                                decoded_password = job.password  # Fallback if not base64
                            
                            active_scheduler.add_job(
                                id=job.id,
                                name=job.name,
                                func=scheduled_collection_job,
                                trigger=trigger,
                                args=[job.username, decoded_password],
                                replace_existing=True,
                                max_instances=1
                            )
                        
                        jobs_added += 1
                        logger.info(f"CLEANUP: Added job {job.name}")
                        
                except Exception as e:
                    logger.error(f"CLEANUP: Failed to add job {job.id}: {e}")
            
            return jsonify({
                'success': True,
                'jobs_added': jobs_added,
                'message': f'Cleanup completed - added {jobs_added} jobs'
            })
            
    except Exception as e:
        logger.error(f"Cleanup failed: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/maintenance/force-sync-jobs', methods=['POST'])
def force_sync_jobs():
    """Simple force sync - emergency job loading for production"""
    try:
        # Get missing jobs from database
        with app.app_context():
            db_jobs = ScheduledJob.query.filter_by(enabled=True).all()
            
            # Use working scheduler - create if needed
            if not scheduler or not scheduler.running:
                from apscheduler.schedulers.background import BackgroundScheduler
                working_scheduler = BackgroundScheduler()
                working_scheduler.start()
                active_scheduler = working_scheduler
                logger.info(f"Working scheduler started on worker {os.getpid()}")
            else:
                active_scheduler = scheduler
            
            jobs_added = 0
            for job in db_jobs:
                try:
                    from apscheduler.triggers.cron import CronTrigger
                    cron_parts = job.cron_expression.split()
                    if len(cron_parts) == 5:
                        minute, hour, day, month, day_of_week = cron_parts
                        trigger = CronTrigger(minute=minute, hour=hour, day=day, month=month, day_of_week=day_of_week)
                        
                        if 'backup' in job.name.lower():
                            active_scheduler.add_job(
                                func=scheduled_backup_job,
                                trigger=trigger,
                                id=job.id,
                                name=job.name,
                                max_instances=1,
                                replace_existing=True
                            )
                        else:
                            # Decode password from base64 for security
                            import base64
                            try:
                                decoded_password = base64.b64decode(job.password).decode('utf-8')
                            except:
                                decoded_password = job.password  # Fallback if not base64
                            
                            active_scheduler.add_job(
                                func=scheduled_collection_job,
                                trigger=trigger,
                                id=job.id,
                                name=job.name,
                                args=[job.username, decoded_password],
                                max_instances=1,
                                replace_existing=True
                            )
                        jobs_added += 1
                        logger.info(f"Added job {job.name} to emergency scheduler")
                except Exception as e:
                    logger.error(f"Failed to add job {job.name}: {e}")
            
            return jsonify({
                'success': True,
                'message': f'Emergency sync completed - added {jobs_added} jobs',
                'jobs_added': jobs_added
            })
            
    except Exception as e:
        logger.error(f"Emergency sync failed: {str(e)}")
        return jsonify({'error': str(e)}), 500



if __name__ == '__main__':
    # Ensure logs directory exists
    os.makedirs('logs', exist_ok=True)

    # Initialize database
    create_tables()

    # Initialize background scheduler that works
    from apscheduler.schedulers.background import BackgroundScheduler
    scheduler = BackgroundScheduler()
    scheduler.start()
    logger.info("BACKGROUND SCHEDULER: Started successfully")
    
    # Mark scheduler as global and auto-load jobs when accessed
    scheduler._auto_load_completed = False
    
    def auto_load_jobs():
        """Auto-load jobs into scheduler when needed"""
        if hasattr(scheduler, '_auto_load_completed') and scheduler._auto_load_completed:
            return True
            
        try:
            from apscheduler.triggers.cron import CronTrigger
            scheduled_jobs = ScheduledJob.query.filter_by(enabled=True).all()
            logger.info(f"AUTO-LOAD: Loading {len(scheduled_jobs)} jobs into scheduler")
            
            for job in scheduled_jobs:
                try:
                    trigger = CronTrigger.from_crontab(job.cron_expression)
                    
                    if 'backup' in job.name.lower():
                        scheduler.add_job(
                            id=job.id,
                            name=job.name,
                            func=scheduled_backup_job,
                            trigger=trigger,
                            replace_existing=True,
                            max_instances=1
                        )
                        logger.info(f"AUTO-LOAD: Added backup job {job.name}")
                    else:
                        # Decode password from base64 for security
                        import base64
                        try:
                            decoded_password = base64.b64decode(job.password).decode('utf-8')
                        except:
                            decoded_password = job.password  # Fallback if not base64
                        
                        scheduler.add_job(
                            id=job.id,
                            name=job.name,
                            func=scheduled_collection_job,
                            trigger=trigger,
                            args=[job.username, decoded_password],
                            replace_existing=True,
                            max_instances=1
                        )
                        logger.info(f"AUTO-LOAD: Added collection job {job.name}")
                        
                except Exception as e:
                    logger.error(f"Failed to auto-load job {job.name}: {e}")
                    
            scheduler._auto_load_completed = True
            logger.info(f"AUTO-LOAD: Completed with {len(scheduler.get_jobs())} jobs")
            return True
            
        except Exception as e:
            logger.error(f"Auto-load failed: {e}")
            return False
    
    # Attach auto-load function to scheduler
    scheduler.auto_load_jobs = auto_load_jobs
    
    # Clear any existing jobs to prevent duplicates on restart
    try:
        existing_jobs = scheduler.get_jobs()
        if existing_jobs:
            # Don't clear the sync monitor
            jobs_to_clear = [job for job in existing_jobs if job.id != 'job_sync_monitor']
            if jobs_to_clear:
                logger.info(f"📅 SCHEDULER: Clearing {len(jobs_to_clear)} existing jobs before setup")
                for job in jobs_to_clear:
                    scheduler.remove_job(job.id)
    except Exception as e:
        logger.warning(f"Could not clear existing jobs: {e}")
    
    # Now load scheduled jobs from database
    setup_scheduled_jobs()

    # Shutdown scheduler on exit
    atexit.register(lambda: scheduler.shutdown())

    # Start Flask app
    logger.info("Starting Switch Log Analyzer on 0.0.0.0:5000")
    app.run(host='0.0.0.0', port=5000, debug=False)
