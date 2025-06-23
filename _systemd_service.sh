#!/bin/bash

# Create systemd service for Switch Log Analyzer
# Run this script as root to install the service

SERVICE_NAME="nsdevlog"
SERVICE_FILE="/etc/systemd/system/${SERVICE_NAME}.service"
APP_DIR="/opt/SCDB"
USER="root"  # Change to your application user
GROUP="root" # Change to your application group

echo "Creating systemd service for Switch Log Analyzer..."

# Create the service file
cat > "$SERVICE_FILE" << EOF
[Unit]
Description=Switch Log Analyzer - Network Switch Log Analysis Platform
After=network.target postgresql.service
Wants=postgresql.service

[Service]
Type=notify
User=$USER
Group=$GROUP
WorkingDirectory=$APP_DIR
Environment=PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
Environment=PYTHONPATH=$APP_DIR
ExecStart=$APP_DIR/venv/bin/gunicorn --config $APP_DIR/simple_gunicorn_config.py main:app

ExecReload=/bin/kill -s HUP $MAINPID
KillMode=mixed
TimeoutStopSec=60
PrivateTmp=true
Restart=always
RestartSec=10

# Relaxed Security settings for container access
NoNewPrivileges=false
ProtectSystem=false
ProtectHome=false
ReadWritePaths=$APP_DIR /var/log/nsdevlog /var/run/nsdevlog /tmp /var/lib/containers
ProtectKernelTunables=false
ProtectKernelModules=false
ProtectControlGroups=false

# Resource limits
LimitNOFILE=65536
LimitNPROC=4096

[Install]
WantedBy=multi-user.target
EOF

# Set proper permissions
chmod 644 "$SERVICE_FILE"
sudo systemctl daemon-reload
sudo systemctl enable $SERVICE_NAME
sudo systemctl start $SERVICE_NAME
sudo systemctl status $SERVICE_NAME
