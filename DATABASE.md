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

### CollectionRun (Tracking Esecuzioni)
- **Status tracking**: running → completed/failed
- **Metadata**: switch processati, entry totali/nuove, tempi esecuzione
- **Error handling**: Messaggi errore dettagliati

### ScheduledJob (Jobs Persistenti)
- **Cron scheduling**: Espressioni cron per automazione
- **Credential management**: Username/password per switch
- **Enable/disable**: Controllo attivazione jobs
