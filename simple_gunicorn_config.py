"""
Simple Gunicorn Configuration - 2 Worker Architecture
Worker 1: Scheduler only
Worker 2: SSH Collections
"""

import os
import logging

# Basic configuration
bind = "0.0.0.0:5000"
workers = 1
worker_class = "sync"
worker_connections = 1000
timeout = 120
keepalive = 5

# Process naming
proc_name = "switch-analyzer"

# Logging
loglevel = "info"
accesslog = "-"
errorlog = "-"

# Worker management
max_requests = 1000
max_requests_jitter = 50
preload_app = True

def on_starting(server):
    """Called just before the master process is initialized"""
    logging.info("Starting Switch Log Analyzer with 2-worker architecture")

def when_ready(server):
    """Called just after the server is started"""
    logging.info("Switch Log Analyzer ready - Worker 1: Scheduler, Worker 2: Collections")

def worker_int(worker):
    """Called just after a worker exited on SIGINT or SIGQUIT"""
    logging.info(f"Worker {worker.pid} interrupted")

def pre_fork(server, worker):
    """Called just before a worker is forked"""
    # Set worker ID environment variable for role assignment (0-based indexing)
    worker_id = worker.age  # Use age directly (0-based)
    os.environ['WORKER_ID'] = str(worker_id)
    if worker_id == 0:
        logging.info(f"Pre-fork Worker {worker_id}: Scheduler worker (PID will be assigned)")
    else:
        logging.info(f"Pre-fork Worker {worker_id}: Collection worker (PID will be assigned)")

def post_fork(server, worker):
    """Called just after a worker has been forked"""
    worker_id = worker.age  # Use 0-based indexing
    if worker_id == 0:
        logging.info(f"Worker {worker_id} (PID {worker.pid}): Scheduler worker started")
    else:
        logging.info(f"Worker {worker_id} (PID {worker.pid}): Collection worker started")

def worker_abort(worker):
    """Called when a worker receives the SIGABRT signal"""
    logging.error(f"Worker {worker.pid} aborted")
