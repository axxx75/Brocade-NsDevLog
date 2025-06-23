#!/bin/bash

# Complete Production Deployment Script
# Manages web application and scheduler

APP_DIR="/opt/SCDB"
VENV_DIR="$APP_DIR/venv"
LOG_DIR="/var/log/nsdevlog"
RUN_DIR="/var/run/nsdevlog"

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

export {http,https,ftp}_proxy=http://sglvmp2000:1124
echo -e "${GREEN}=== Switch Log Analyzer Production Deployment ===${NC}"
cd $APP_DIR

case "$1" in
        
    logs)
        echo -e "${GREEN}=== Recent Logs ===${NC}"
        
        echo -e "${YELLOW}Web Application Access Log:${NC}"
        tail -20 "$LOG_DIR/access.log" 2>/dev/null || echo "No access logs"
        
        echo ""
        echo -e "${YELLOW}Web Application Error Log:${NC}"
        tail -20 "$LOG_DIR/error.log" 2>/dev/null || echo "No error logs"
        
        echo ""
        echo -e "${YELLOW}Scheduler Log:${NC}"
        tail -20 "$LOG_DIR/scheduler.log" 2>/dev/null || echo "No scheduler logs"
    ;;
        
    test)
        echo -e "${GREEN}=== Testing Services ===${NC}"
        
        # Test web application
        echo -e "${YELLOW}Testing web application...${NC}"
        if curl -s http://localhost:5000 >/dev/null; then
            echo "✓ Web application responding"
        else
            echo "✗ Web application not responding"
        fi
        
        # Test scheduler status via API
        echo -e "${YELLOW}Testing scheduler API...${NC}"
        if curl -s http://localhost:5000/api/scheduler/status >/dev/null; then
            echo "✓ Scheduler API responding"
        else
            echo "✗ Scheduler API not responding"
        fi
    ;;
        
    setup)
        echo -e "${GREEN}=== Initial Setup ===${NC}"
        
        # Create directories
        echo "Creating directories..."
        sudo mkdir -p "$LOG_DIR" "$RUN_DIR"
        sudo chown -R $(whoami):$(whoami) "$LOG_DIR" "$RUN_DIR"
        
        # Create virtual environment if needed
        if [ ! -d "$VENV_DIR" ]; then
           echo "Creating virtual environment..."
           python3.8 -m venv "$VENV_DIR"

           # Activate and install dependencies
           echo "Installing dependencies..."
           source "$VENV_DIR/bin/activate"
           pip3.8 install --upgrade pip
           pip3.8 install -r requirements.txt
           echo -e "${GREEN}Setup Enviroment completed!${NC}"
        fi
        
        # Create DB
        echo -n "Vuoi inizializzare il database PostgreSQL? [y/N]: "
        read risposta
        if [[ "$risposta" =~ ^[Yy]$ ]]; then

           echo "Create/Inizialize DB Postgress..."
           cd $APP_DIR || exit 1
           sudo -u postgres psql -c "DROP DATABASE IF EXISTS switch_analyzer;"
           sudo -u postgres psql -c "CREATE DATABASE switch_analyzer OWNER analyzer_user;"
           sudo -u postgres psql -c "GRANT ALL PRIVILEGES ON DATABASE switch_analyzer TO analyzer_user;"
           sudo -u postgres psql -c "ALTER USER analyzer_user CREATEDB;"

           python3.8 -c "
           from main import app
           from models import db
           with app.app_context():
               db.create_all()
               print('✅ Tabelle del database create con successo!')
           "
           echo -e "${GREEN}Inizialize DB completed!${NC}"
        else
           echo -e "${RED}Inizializzazione del DB saltata.${NC}"
        fi

        # Installazione servizio /etc/systemd/system/nsdevlog.service
        echo -n "Vuoi installare il servizio in systemd? [y/N]: "
        read risposta
        if [[ "$risposta" =~ ^[Yy]$ ]]; then
            echo "Installazione del servizio systemd in corso..."
            if sh _systemd_service.sh; then
                echo -e "${GREEN}Installazione del servizio completata con successo!${NC}"
            else
                echo -e "${RED}Errore durante l'installazione del servizio!${NC}"
                exit 1
            fi
        else
            echo -e "${YELLOW}Installazione del servizio saltata.${NC}"
        fi
    ;;

    status)
      journalctl -u nsdevlog.service -f -o cat
    ;;

        
    *)
        echo "Usage: $0 {start|stop|restart|status|logs|reload-scheduler|test|setup}"
        echo ""
        echo "Commands:"
        echo "  setup            - Initial setup (create dirs, install dependencies)"
        echo "  start            - Start nsdevlog (web and scheduler)"
        echo "  stop             - Stop nsdevlog services"
        echo "  restart          - Restart nsdevlog services"
        echo "  status           - Show status of services"
        echo "  logs             - Show recent logs from services"
        echo "  test             - Test if services are responding"
        echo ""
        exit 1
        ;;
esac
