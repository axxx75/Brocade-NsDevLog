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
Environment=PATH=$APP_DIR/venv/bin
ExecStart=$APP_DIR/venv/bin/gunicorn --config $APP_DIR/gunicorn_config.py main:app
ExecReload=/bin/kill -s HUP \$MAINPID
KillMode=mixed
TimeoutStopSec=5
PrivateTmp=true
Restart=always
RestartSec=10

# Security settings
NoNewPrivileges=true
ProtectSystem=strict
ProtectHome=true
ReadWritePaths=$APP_DIR /var/log/nsdevlog /var/run/nsdevlog /tmp
ProtectKernelTunables=true
ProtectKernelModules=true
ProtectControlGroups=true

# Resource limits
LimitNOFILE=65536
LimitNPROC=4096

[Install]
WantedBy=multi-user.target
EOF

# Set proper permissions
chmod 644 "$SERVICE_FILE"

echo "Service file created at: $SERVICE_FILE"
echo ""
echo "To enable and start the service, run:"
echo "  sudo systemctl daemon-reload"
echo "  sudo systemctl enable $SERVICE_NAME"
echo "  sudo systemctl start $SERVICE_NAME"
echo ""
echo "To check service status:"
echo "  sudo systemctl status $SERVICE_NAME"
echo ""
echo "To view logs:"
echo "  sudo journalctl -u $SERVICE_NAME -f"
