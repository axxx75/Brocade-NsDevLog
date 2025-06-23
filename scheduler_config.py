"""
Scheduler Configuration for Switch Log Analyzer
Centralized configuration for APScheduler settings and job management
"""

import os
from datetime import datetime

class SchedulerConfig:
    """Centralized scheduler configuration"""
    
    # Basic scheduler settings
    SCHEDULER_TYPE = 'background'  # 'background' or 'blocking'
    TIMEZONE = 'UTC'
    
    # Job execution settings
    MAX_INSTANCES = 1  # Prevent duplicate job executions
    COALESCE = True    # Combine multiple pending executions
    MISFIRE_GRACE_TIME = 300  # 5 minutes grace time for missed jobs
    
    # Database job store configuration
    JOB_DEFAULTS = {
        'coalesce': True,
        'max_instances': MAX_INSTANCES,
        'misfire_grace_time': MISFIRE_GRACE_TIME
    }
    
    # Thread pool settings
    THREAD_POOL_MAX_WORKERS = 2  # Limit concurrent job execution
    
    # Backup job configuration
    BACKUP_SCHEDULE = {
        'hour': 2,      # Run at 2 AM
        'minute': 0,
        'timezone': TIMEZONE
    }
    
    # Collection job defaults
    COLLECTION_DEFAULTS = {
        'timeout': 3600,  # 1 hour timeout
        'retry_attempts': 3,
        'retry_delay': 300  # 5 minutes between retries
    }
    
    # Emergency scheduler settings
    EMERGENCY_SCHEDULER_ENABLED = True
    AUTO_RECOVERY_ENABLED = True
    
    # Production settings
    DISABLE_INTERNAL_SCHEDULER = os.getenv('DISABLE_INTERNAL_SCHEDULER', 'false').lower() == 'true'
    FORCE_SINGLE_WORKER = True  # Force single worker mode for stability
    
    @classmethod
    def get_scheduler_config(cls):
        """Get complete scheduler configuration dictionary"""
        return {
            'job_defaults': cls.JOB_DEFAULTS,
            'timezone': cls.TIMEZONE,
            'executors': {
                'default': {
                    'type': 'threadpool',
                    'max_workers': cls.THREAD_POOL_MAX_WORKERS
                }
            },
            'job_stores': {
                'default': {
                    'type': 'memory'
                }
            }
        }
    
    @classmethod
    def get_backup_job_config(cls):
        """Get backup job configuration"""
        return {
            'trigger': 'cron',
            'hour': cls.BACKUP_SCHEDULE['hour'],
            'minute': cls.BACKUP_SCHEDULE['minute'],
            'timezone': cls.BACKUP_SCHEDULE['timezone'],
            'id': 'automated_backup',
            'name': 'Automated Database Backup',
            'max_instances': 1,
            'coalesce': True,
            'replace_existing': True
        }
    
    @classmethod
    def get_collection_job_config(cls, cron_expression, job_id, job_name):
        """Get collection job configuration"""
        return {
            'trigger': 'cron',
            'id': job_id,
            'name': job_name,
            'max_instances': cls.MAX_INSTANCES,
            'coalesce': cls.COALESCE,
            'misfire_grace_time': cls.MISFIRE_GRACE_TIME,
            'replace_existing': True
        }
    
    @classmethod
    def is_production_mode(cls):
        """Check if running in production mode"""
        return cls.DISABLE_INTERNAL_SCHEDULER or os.getenv('GUNICORN_CMD_ARGS') is not None
    
    @classmethod
    def get_log_config(cls):
        """Get logging configuration for scheduler"""
        return {
            'level': 'INFO',
            'format': '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            'handlers': ['console']
        }

# Pre-defined job schedules
PREDEFINED_SCHEDULES = {
    'hourly': '0 * * * *',
    'daily': '0 2 * * *',
    'weekly': '0 2 * * 0',
    'monthly': '0 2 1 * *'
}

# Job priorities (for future implementation)
JOB_PRIORITIES = {
    'backup': 1,      # Highest priority
    'collection': 2,  # Normal priority
    'cleanup': 3,     # Lower priority
    'maintenance': 4  # Lowest priority
}
