"""
Simple Direct Scheduler - Production-ready scheduler implementation
Provides auto-initialization and direct job management
"""

import logging
from datetime import datetime
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from scheduler_config import SchedulerConfig

logger = logging.getLogger(__name__)

class DirectScheduler:
    """Direct scheduler with auto-initialization and configuration management"""
    
    def __init__(self):
        self.scheduler = None
        self._initialized = False
        self._auto_load_completed = False
        
    def init_and_start(self):
        """Initialize and start the scheduler if not already running"""
        if self._initialized and self.scheduler and self.scheduler.running:
            return True
            
        try:
            # Create scheduler with configuration
            config = SchedulerConfig.get_scheduler_config()
            self.scheduler = BackgroundScheduler(**config)
            self.scheduler.start()
            self._initialized = True
            logger.info("DirectScheduler initialized and started")
            return True
        except Exception as e:
            logger.error(f"Failed to initialize DirectScheduler: {e}")
            return False
    
    @property
    def running(self):
        """Check if scheduler is running"""
        if not self.scheduler:
            return False
        return self.scheduler.running
    
    def add_job(self, func, trigger=None, id=None, name=None, **kwargs):
        """Add job to scheduler"""
        if not self._initialized:
            self.init_and_start()
        
        if not self.scheduler:
            return None
            
        # Apply configuration defaults
        job_config = {
            'max_instances': SchedulerConfig.MAX_INSTANCES,
            'coalesce': SchedulerConfig.COALESCE,
            'misfire_grace_time': SchedulerConfig.MISFIRE_GRACE_TIME,
            'replace_existing': True
        }
        job_config.update(kwargs)
        
        return self.scheduler.add_job(
            func=func,
            trigger=trigger,
            id=id,
            name=name,
            **job_config
        )
    
    def remove_job(self, job_id):
        """Remove job from scheduler"""
        if not self.scheduler:
            return False
        try:
            self.scheduler.remove_job(job_id)
            return True
        except Exception as e:
            logger.error(f"Failed to remove job {job_id}: {e}")
            return False
    
    def get_job(self, job_id):
        """Get job by ID"""
        if not self.scheduler:
            return None
        try:
            return self.scheduler.get_job(job_id)
        except Exception:
            return None
    
    def get_jobs(self):
        """Get all jobs"""
        if not self.scheduler:
            return []
        try:
            return self.scheduler.get_jobs()
        except Exception:
            return []
    
    def pause_job(self, job_id):
        """Pause a job"""
        if not self.scheduler:
            return False
        try:
            self.scheduler.pause_job(job_id)
            return True
        except Exception as e:
            logger.error(f"Failed to pause job {job_id}: {e}")
            return False
    
    def resume_job(self, job_id):
        """Resume a paused job"""
        if not self.scheduler:
            return False
        try:
            self.scheduler.resume_job(job_id)
            return True
        except Exception as e:
            logger.error(f"Failed to resume job {job_id}: {e}")
            return False
    
    def shutdown(self, wait=True):
        """Shutdown the scheduler"""
        if self.scheduler:
            try:
                self.scheduler.shutdown(wait=wait)
                logger.info("DirectScheduler shutdown completed")
            except Exception as e:
                logger.error(f"Error during scheduler shutdown: {e}")
        self._initialized = False
    
    def remove_all_jobs(self):
        """Remove all jobs from scheduler"""
        if not self.scheduler:
            return False
        try:
            self.scheduler.remove_all_jobs()
            return True
        except Exception as e:
            logger.error(f"Failed to remove all jobs: {e}")
            return False
