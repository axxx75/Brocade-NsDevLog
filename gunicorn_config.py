"""
Gunicorn Configuration for Switch Log Analyzer
Optimized for production deployment with security enhancements
"""

import multiprocessing
import os

# Server socket
bind = "0.0.0.0:5000"
backlog = 2048

# Worker processes - Single worker to prevent scheduler duplication
workers = 1
worker_class = "sync"
worker_connections = 1000
timeout = 300  # Increased to 5 minutes for long-running collection operations
keepalive = 2

# Restart workers after this many requests, to help prevent memory leaks
max_requests = 1000
max_requests_jitter = 50

# Graceful shutdown timeout
graceful_timeout = 60  # Allow 60 seconds for graceful worker shutdown

# Security settings (commented out - not supported in older Gunicorn versions)
# limit_request_line = 4094
# limit_request_fields = 100
# limit_request_field_size = 8190

# Logging
accesslog = "/var/log/nsdevlog/access.log"
errorlog = "/var/log/nsdevlog/error.log"
loglevel = "info"
access_log_format = '%(h)s %(l)s %(u)s %(t)s "%(r)s" %(s)s %(b)s "%(f)s" "%(a)s" %(D)s'

# Process naming
proc_name = "nsdevlog"

# Server mechanics
daemon = False
pidfile = "/var/run/nsdevlog/gunicorn.pid"
user = None
group = None
tmp_upload_dir = None

# SSL (uncomment if using HTTPS)
# keyfile = "/path/to/your/private.key"
# certfile = "/path/to/your/certificate.crt"

# Preload application for better performance
preload_app = True

# Worker timeout for long-running operations
graceful_timeout = 120

def when_ready(server):
    server.log.info("Switch Log Analyzer server is ready. Listening on: %s", server.address)

def worker_int(worker):
    worker.log.info("worker received INT or QUIT signal")

def pre_fork(server, worker):
    server.log.info("Worker spawned (pid: %s)", worker.pid)

def post_fork(server, worker):
    server.log.info("Worker spawned (pid: %s)", worker.pid)
