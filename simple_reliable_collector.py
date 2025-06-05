#!/usr/bin/env python3
"""
Simple, Reliable Collection System - Direct database insertion
"""
import logging
import uuid
from datetime import datetime
from typing import List, Dict
from models import db, LogEntry, SwitchStatus, CollectionRun
from simple_switch_collector import SimpleLogCollector
from config import Config

logger = logging.getLogger(__name__)

def run_simple_collection(username: str, password: str) -> Dict:
    """Simple collection that directly inserts data without complex filtering"""
    collection_id = str(uuid.uuid4())
    
    # Create collection record
    collection_run = CollectionRun(
        id=collection_id,
        started_at=datetime.utcnow(),
        status='running',
        switches_processed=[],
        total_entries=0,
        new_entries=0
    )
    
    db.session.add(collection_run)
    db.session.commit()
    
    logger.info(f"Starting simple collection {collection_id}")
    
    try:
        collector = SimpleLogCollector(username, password)
        switches = Config.load_switches()
        
        total_inserted = 0
        switches_processed = []
        
        for switch_info in switches:
            switch_name = switch_info.split(':')[0] if ':' in switch_info else switch_info
            logger.info(f"Processing: {switch_name}")
            
            try:
                # Collect entries from switch
                switch_entries = collector.collect_from_switch_simple(switch_info)
                
                if not switch_entries:
                    logger.warning(f"{switch_name}: No entries collected")
                    continue
                
                logger.info(f"{switch_name}: Collected {len(switch_entries)} entries")
                
                # Get last entry timestamp for this switch to avoid duplicates
                last_entry = db.session.query(LogEntry.timestamp).filter_by(
                    switch_name=switch_name
                ).order_by(LogEntry.timestamp.desc()).first()
                
                last_timestamp = last_entry[0] if last_entry else None
                
                # Insert entries directly
                inserted_count = 0
                for entry in switch_entries:
                    try:
                        entry_time = datetime.strptime(entry['timestamp'], '%a %b %d %Y %H:%M:%S.%f')
                        
                        # Only insert if newer than last entry or if first collection
                        if not last_timestamp or entry_time > last_timestamp:
                            log_entry = LogEntry(
                                timestamp=entry_time,
                                switch_name=switch_name,
                                context=entry.get('context', 0),
                                event_type=entry.get('event', 'Unknown'),
                                wwn=entry.get('port_wwn') or entry.get('node_wwn'),
                                port_info=entry.get('slot_port', ''),
                                raw_line=entry.get('raw_line', ''),
                                alias="N/A",
                                node_symbol="N/A",
                                collection_id=collection_id
                            )
                            
                            db.session.add(log_entry)
                            inserted_count += 1
                            
                            # Commit every 100 entries
                            if inserted_count % 100 == 0:
                                db.session.commit()
                                logger.info(f"{switch_name}: Inserted {inserted_count} entries")
                    
                    except Exception as e:
                        logger.error(f"Failed to insert entry: {e}")
                        continue
                
                # Final commit for remaining entries
                db.session.commit()
                total_inserted += inserted_count
                
                # Update switch status
                switch_status = SwitchStatus.query.filter_by(switch_name=switch_name).first()
                if not switch_status:
                    switch_status = SwitchStatus(
                        switch_name=switch_name,
                        last_collection_date=datetime.utcnow(),
                        last_collection_id=collection_id,
                        last_entry_count=inserted_count,
                        status='active'
                    )
                    db.session.add(switch_status)
                else:
                    switch_status.last_collection_date = datetime.utcnow()
                    switch_status.last_collection_id = collection_id
                    switch_status.last_entry_count = inserted_count
                    switch_status.status = 'active'
                
                db.session.commit()
                switches_processed.append(switch_name)
                
                logger.info(f"{switch_name}: Successfully inserted {inserted_count} new entries")
                
            except Exception as e:
                logger.error(f"{switch_name}: Collection failed - {e}")
                db.session.rollback()
                continue
        
        # Update collection record
        collection_run.status = 'completed'
        collection_run.completed_at = datetime.utcnow()
        collection_run.total_entries = total_inserted
        collection_run.new_entries = total_inserted
        collection_run.switches_processed = switches_processed
        db.session.commit()
        
        # Verify actual database count
        actual_count = LogEntry.query.count()
        logger.info(f"Collection completed: {total_inserted} entries inserted, {actual_count} total in database")
        
        return {
            'success': True,
            'collection_id': collection_id,
            'switches_processed': len(switches_processed),
            'new_entries': total_inserted,
            'database_count': actual_count
        }
        
    except Exception as e:
        logger.error(f"Collection failed: {e}")
        collection_run.status = 'failed'
        collection_run.error_message = str(e)
        collection_run.completed_at = datetime.utcnow()
        db.session.commit()
        
        return {
            'success': False,
            'error': str(e),
            'collection_id': collection_id
        }
