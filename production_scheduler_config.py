"""
Production Scheduler Configuration
Handles scheduler worker designation in Gunicorn multi-worker environment
"""
import os
import logging
from apscheduler.schedulers.background import BackgroundScheduler

logger = logging.getLogger(__name__)

class ProductionSchedulerManager:
    """
    Simplified production scheduler that uses file-based worker coordination
    to avoid race conditions in Gunicorn multi-worker environments
    """
    
    def __init__(self):
        self.scheduler = None
        self.is_scheduler_worker = self._determine_scheduler_worker()
        self.worker_pid = os.getpid()
        
    def _determine_scheduler_worker(self):
        """
        With single worker configuration, always run scheduler
        """
        current_pid = os.getpid()
        logger.info(f"📅 SCHEDULER: Single worker mode - PID {current_pid} running scheduler")
        return True
    
    def init_scheduler(self):
        """Initialize scheduler only in designated worker"""
        if not self.is_scheduler_worker:
            logger.info(f"📅 SCHEDULER: Worker {self.worker_pid} skipping scheduler init")
            return False
            
        if self.scheduler is None:
            try:
                self.scheduler = BackgroundScheduler(
                    job_defaults={
                        'coalesce': True,  # Combine multiple pending executions
                        'max_instances': 1,  # Only one instance per job
                        'misfire_grace_time': 300  # 5 minutes grace for missed jobs
                    },
                    executors={
                        'default': {'type': 'threadpool', 'max_workers': 1}  # Reduced to 1 worker
                    }
                )
                logger.info(f"📅 SCHEDULER: Initialized in worker {self.worker_pid}")
                return True
            except Exception as e:
                logger.error(f"📅 SCHEDULER: Failed to initialize: {e}")
                return False
        return True
    
    def start(self):
        """Start scheduler if this is the designated worker"""
        if not self.is_scheduler_worker:
            return False
            
        if self.scheduler and not self.scheduler.running:
            try:
                self.scheduler.start()
                logger.info(f"📅 SCHEDULER: Started in worker {self.worker_pid}")
                return True
            except Exception as e:
                logger.error(f"📅 SCHEDULER: Failed to start: {e}")
                return False
        return False
    
    def shutdown(self):
        """Shutdown scheduler and clean up lock file"""
        if self.scheduler and self.scheduler.running:
            try:
                self.scheduler.shutdown()
                logger.info(f"📅 SCHEDULER: Shutdown in worker {self.worker_pid}")
                
                # Clean up lock file if we own it
                lock_file = '/tmp/scheduler_worker.lock'
                if os.path.exists(lock_file):
                    try:
                        with open(lock_file, 'r') as f:
                            if f.read().strip() == str(self.worker_pid):
                                os.remove(lock_file)
                                logger.info(f"📅 SCHEDULER: Cleaned up lock file")
                    except Exception as e:
                        logger.warning(f"📅 SCHEDULER: Failed to clean lock file: {e}")
                        
                return True
            except Exception as e:
                logger.error(f"📅 SCHEDULER: Failed to shutdown: {e}")
                return False
        return False
    
    def add_job(self, *args, **kwargs):
        """Add job to scheduler if this is the designated worker"""
        if not self.is_scheduler_worker:
            logger.debug(f"📅 SCHEDULER: Worker {self.worker_pid} skipping job add")
            return None
            
        if self.scheduler is None:
            logger.warning(f"📅 SCHEDULER: Scheduler not initialized in worker {self.worker_pid}")
            if self.init_scheduler() and self.start():
                logger.info(f"📅 SCHEDULER: Re-initialized scheduler in worker {self.worker_pid}")
            else:
                logger.error(f"📅 SCHEDULER: Failed to re-initialize scheduler")
                return None
                
        try:
            result = self.scheduler.add_job(*args, **kwargs)
            logger.info(f"📅 SCHEDULER: Job added successfully in worker {self.worker_pid}")
            return result
        except Exception as e:
            logger.error(f"📅 SCHEDULER: Failed to add job: {e}")
            return None
    
    def remove_job(self, job_id):
        """Remove job from scheduler"""
        if not self.is_scheduler_worker or not self.scheduler:
            return False
            
        try:
            self.scheduler.remove_job(job_id)
            return True
        except Exception as e:
            logger.error(f"📅 SCHEDULER: Failed to remove job {job_id}: {e}")
            return False
    
    def get_job(self, job_id):
        """Get job from scheduler"""
        if not self.is_scheduler_worker or not self.scheduler:
            return None
            
        try:
            return self.scheduler.get_job(job_id)
        except Exception as e:
            logger.error(f"📅 SCHEDULER: Failed to get job {job_id}: {e}")
            return None
    
    def get_jobs(self):
        """Get all jobs from scheduler"""
        if not self.is_scheduler_worker or not self.scheduler:
            return []
            
        try:
            return self.scheduler.get_jobs()
        except Exception as e:
            logger.error(f"📅 SCHEDULER: Failed to get jobs: {e}")
            return []
    
    def remove_all_jobs(self):
        """Remove all jobs from scheduler"""
        if not self.is_scheduler_worker or not self.scheduler:
            return False
            
        try:
            self.scheduler.remove_all_jobs()
            return True
        except Exception as e:
            logger.error(f"📅 SCHEDULER: Failed to remove all jobs: {e}")
            return False
    
    @property
    def running(self):
        """Check if scheduler is running"""
        if not self.is_scheduler_worker or not self.scheduler:
            return False
        return self.scheduler.running
    
    def pause_job(self, job_id):
        """Pause a job"""
        if not self.is_scheduler_worker or not self.scheduler:
            return False
            
        try:
            self.scheduler.pause_job(job_id)
            return True
        except Exception as e:
            logger.error(f"📅 SCHEDULER: Failed to pause job {job_id}: {e}")
            return False
    
    def resume_job(self, job_id):
        """Resume a job"""
        if not self.is_scheduler_worker or not self.scheduler:
            return False
            
        try:
            self.scheduler.resume_job(job_id)
            return True
        except Exception as e:
            logger.error(f"📅 SCHEDULER: Failed to resume job {job_id}: {e}")
            return False
