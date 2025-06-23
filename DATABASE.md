# 📚 Configurazione di PostgreSQL

## ✨ Requisiti
- PostgreSQL installato (versione ≥ 12)
- Accesso come utente `postgres` o privilegi `sudo`
- Utente e database dedicati all'applicazione NsDevLog

## 📦 1. Installazione di PostgreSQL (Red Hat / CentOS / Fedora)
Installare i sorgenti necessari e inizializzare il DB
```bash
sudo dnf install postgresql-server postgresql-contrib
sudo postgresql-setup --initdb
sudo systemctl enable --now postgresql
```

## 📦 2. Creazione del DB PostgreSQL per l'app
Accedi alla shell di PostgreSQL:
```bash
sudo -u postgres psql
```

Esegui i comandi seguenti per creare utente e database:
```bash
-- Crea un utente (modifica 'analyzer_user' e 'password' come necessario)
CREATE USER analyzer_user WITH PASSWORD 'password';

-- Crea il database (modifica 'switch_analyzer' come desideri)
CREATE DATABASE switch_analyzer OWNER analyzer_user;

-- Concedi privilegi
GRANT ALL PRIVILEGES ON DATABASE switch_analyzer TO analyzer_user;

-- (Opzionale) consenti al tuo utente di creare altri DB
ALTER USER analyzer_user CREATEDB;

-- Esci dalla shell:
\q
```

## 📦 3. Permessi di accesso (pg_hba.conf)
Modifica il file per permettere l’accesso locale:
```bash
sudo vi /var/lib/pgsql/data/pg_hba.conf
```

Aggiungi o modifica la riga:
```bash
local   all             analyzer_user                            md5
```

Poi riavvia PostgreSQL:
```bash
sudo systemctl restart postgresql
```

## 📦 4. Test della connessione
```bash
psql -U analyzer_user -d switch_analyzer -h localhost
```

## 🔨 5. Inizializzazione del database in Flask
```sql
cd $APP_DIR
python3.8 -c "
from main import app
from models import db
with app.app_context():
    db.create_all()
    print('✅ Tabelle del database create con successo!')
"
```

## 📌 Note aggiuntive
Assicurati che l’utente sia lo stesso definito nella configurazione dell’app, nel file 



## 📊 Database Schema

### LogEntry (Tabella Principale)
- **Indici ottimizzati**: timestamp+switch, WWN+timestamp, alias, node_symbol
- **Campi chiave**: timestamp, switch_name, context, event_type, wwn, alias, node_symbol
- **Performance**: Supporta milioni di record con query sub-secondo

```sql
-- Indici compositi per performance
CREATE INDEX idx_timestamp_switch ON log_entries(timestamp, switch_name);
CREATE INDEX idx_wwn_timestamp ON log_entries(wwn, timestamp);
CREATE INDEX idx_collection_switch ON log_entries(collection_id, switch_name);
```

### CollectionRun (Tabella Tracking Esecuzioni)
- **Status tracking**: running → completed/failed
- **Metadata**: switch processati, entry totali/nuove, tempi esecuzione
- **Error handling**: Messaggi errore dettagliati

### ScheduledJob (Tabella Jobs Persistenti)
- **Cron scheduling**: Espressioni cron per automazione
- **Credential management**: Username/password per switch
- **Enable/disable**: Controllo attivazione jobs


🧪
