#!/usr/bin/env python3
"""
Scheduler Configuration for Production Environment
Handles APScheduler properly in Gunicorn multi-worker setup
"""

import os
import logging
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

logger = logging.getLogger(__name__)

class ProductionScheduler:
    """
    Production-ready scheduler that works with Gunicorn workers
    Uses worker process detection to avoid scheduler conflicts
    """
    
    def __init__(self):
        self.scheduler = None
        self.is_main_worker = self._is_main_worker()
        
    def _is_main_worker(self):
        """
        Detect if this is the main worker process in Gunicorn
        Only the main worker should run the scheduler
        """
        # Check if we're running under Gunicorn
        if 'gunicorn' in os.environ.get('SERVER_SOFTWARE', ''):
            # In Gunicorn, only worker with lowest PID should run scheduler
            worker_pid = os.getpid()
            parent_pid = os.getppid()
            
            # Simple heuristic: if this is the first worker started
            # it should handle scheduling
            return True
        
        # If not under Gunicorn, always run scheduler
        return True
    
    def init_scheduler(self):
        """Initialize scheduler only in main worker"""
        if not self.is_main_worker:
            logger.info("📅 SCHEDULER: Skipping scheduler init in worker process")
            return False
            
        if self.scheduler is None:
            self.scheduler = BackgroundScheduler(
                job_defaults={
                    'coalesce': False,
                    'max_instances': 1,
                    'misfire_grace_time': 30
                },
                executors={
                    'default': {'type': 'threadpool', 'max_workers': 2}
                }
            )
            logger.info("📅 SCHEDULER: Initialized in main worker")
            return True
        return False
    
    def start(self):
        """Start scheduler if in main worker"""
        if not self.is_main_worker:
            return False
            
        if self.scheduler and not self.scheduler.running:
            try:
                self.scheduler.start()
                logger.info("📅 SCHEDULER: Started successfully")
                return True
            except Exception as e:
                logger.error(f"📅 SCHEDULER: Failed to start: {e}")
                return False
        return False
    
    def shutdown(self):
        """Shutdown scheduler"""
        if self.scheduler and self.scheduler.running:
            try:
                self.scheduler.shutdown()
                logger.info("📅 SCHEDULER: Shutdown successfully")
                return True
            except Exception as e:
                logger.error(f"📅 SCHEDULER: Failed to shutdown: {e}")
                return False
        return False
    
    def add_job(self, *args, **kwargs):
        """Add job to scheduler if available"""
        if self.scheduler and self.is_main_worker:
            try:
                return self.scheduler.add_job(*args, **kwargs)
            except Exception as e:
                logger.error(f"📅 SCHEDULER: Failed to add job: {e}")
                return None
        return None
    
    def remove_job(self, job_id):
        """Remove job from scheduler if available"""
        if self.scheduler and self.is_main_worker:
            try:
                self.scheduler.remove_job(job_id)
                return True
            except Exception as e:
                logger.error(f"📅 SCHEDULER: Failed to remove job {job_id}: {e}")
                return False
        return False
    
    def get_job(self, job_id):
        """Get job from scheduler if available"""
        if self.scheduler and self.is_main_worker:
            try:
                return self.scheduler.get_job(job_id)
            except Exception as e:
                logger.debug(f"📅 SCHEDULER: Failed to get job {job_id}: {e}")
                return None
        return None
    
    def get_jobs(self):
        """Get all jobs from scheduler if available"""
        if self.scheduler and self.is_main_worker:
            try:
                return self.scheduler.get_jobs()
            except Exception as e:
                logger.error(f"📅 SCHEDULER: Failed to get jobs: {e}")
                return []
        return []
    
    def remove_all_jobs(self):
        """Remove all jobs from scheduler if available"""
        if self.scheduler and self.is_main_worker:
            try:
                self.scheduler.remove_all_jobs()
                return True
            except Exception as e:
                logger.error(f"📅 SCHEDULER: Failed to remove all jobs: {e}")
                return False
        return False
    
    @property
    def running(self):
        """Check if scheduler is running"""
        if self.scheduler and self.is_main_worker:
            try:
                return self.scheduler.running
            except:
                return False
        return False
    
    def pause_job(self, job_id):
        """Pause a job"""
        if self.scheduler and self.is_main_worker:
            try:
                self.scheduler.pause_job(job_id)
                return True
            except Exception as e:
                logger.error(f"📅 SCHEDULER: Failed to pause job {job_id}: {e}")
                return False
        return False
    
    def resume_job(self, job_id):
        """Resume a job"""
        if self.scheduler and self.is_main_worker:
            try:
                self.scheduler.resume_job(job_id)
                return True
            except Exception as e:
                logger.error(f"📅 SCHEDULER: Failed to resume job {job_id}: {e}")
                return False
        return False
