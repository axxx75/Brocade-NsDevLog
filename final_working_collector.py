"""
Final Working Collection System - Parallel processing with 4 concurrent switches
"""

import os
import logging
import uuid
import threading
import concurrent.futures
from datetime import datetime
from typing import Dict, List, Optional, Tuple
from flask import current_app
from models import db, LogEntry, CollectionRun, SwitchStatus
from simple_switch_collector import SimpleLogCollector
from config import Config
from device_lookup_optimized import lookup_alias_and_node_symbol, extract_slot_port_from_entry, refresh_device_port_data

logger = logging.getLogger(__name__)

# Thread-local storage for database sessions
thread_local = threading.local()

def get_thread_db_session():
    """Get a thread-local database session"""
    if not hasattr(thread_local, 'session'):
        from flask import current_app
        thread_local.session = current_app.extensions['sqlalchemy'].db.session
    return thread_local.session

def process_single_switch(switch_info: str, username: str, password: str, collection_id: str, app) -> Dict:
    """Process a single switch in parallel"""
    # Extract actual switch name
    parts = switch_info.split(':')
    if len(parts) >= 2:
        actual_switch_name = parts[1]
    else:
        actual_switch_name = switch_info
    
    logger.info(f"Processing switch: {actual_switch_name}")
    
    # Create application context for this thread
    with app.app_context():
        try:
            collector = SimpleLogCollector(username, password)
            switch_entries = collector.collect_from_switch_simple(switch_info)
            
            if not switch_entries:
                logger.warning(f"{actual_switch_name}: No entries collected")
                return {
                    'switch_name': actual_switch_name,
                    'success': False,
                    'inserted_count': 0,
                    'total_entries': 0,
                    'error': 'No entries collected'
                }
            
            logger.info(f"{actual_switch_name}: Collected {len(switch_entries)} entries")
            
            # Get last entry timestamp for THIS SPECIFIC SWITCH
            last_entry = db.session.query(LogEntry.timestamp).filter_by(
                switch_name=actual_switch_name
            ).order_by(LogEntry.timestamp.desc()).first()
            
            last_timestamp = last_entry[0] if last_entry else None
            if last_timestamp:
                logger.info(f"{actual_switch_name}: Last entry timestamp: {last_timestamp}")
            else:
                logger.info(f"{actual_switch_name}: First collection (no previous entries)")
            
            # Insert entries
            inserted_count = 0
            for entry in switch_entries:
                try:
                    entry_time = datetime.strptime(entry['timestamp'], '%a %b %d %Y %H:%M:%S.%f')
                    
                    # Only insert if newer than last entry or if first collection
                    if not last_timestamp or entry_time > last_timestamp:
                        # Extract WWN and port info for lookup
                        wwn = entry.get('port_wwn') or entry.get('node_wwn')
                        port_info = entry.get('slot_port', '') or entry.get('port_info', '')
                        
                        # Extract slot and port numbers for device_port.json lookup
                        slot_number, port_number = extract_slot_port_from_entry(entry)
                        alias, node_symbol = None, None
                        
                        if wwn and slot_number is not None and port_number is not None:
                            alias, node_symbol = lookup_alias_and_node_symbol(
                                actual_switch_name, slot_number, port_number, wwn
                            )
                        
                        log_entry = LogEntry(
                            timestamp=entry_time,
                            switch_name=actual_switch_name,
                            context=entry.get('context'),
                            event_type=entry.get('event'),  # Fix: use 'event' from parser
                            wwn=wwn,
                            port_info=port_info,
                            raw_line=entry.get('raw_line', ''),
                            alias=alias,
                            node_symbol=node_symbol,
                            collection_id=collection_id
                        )
                        
                        db.session.add(log_entry)
                        inserted_count += 1
                        
                        if inserted_count % 100 == 0:
                            db.session.commit()
                            logger.info(f"{actual_switch_name}: Inserted {inserted_count} entries so far")
                            
                except Exception as e:
                    logger.error(f"{actual_switch_name}: Error processing entry: {str(e)}")
            
            # Final commit for this switch
            if inserted_count > 0:
                db.session.commit()
            
            logger.info(f"{actual_switch_name}: Successfully inserted {inserted_count} new entries")
            
            # Update switch status
            switch_status = SwitchStatus.query.filter_by(switch_name=actual_switch_name).first()
            if not switch_status:
                switch_status = SwitchStatus(
                    switch_name=actual_switch_name,
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
                switch_status.last_error = None
            
            db.session.commit()
            
            return {
                'switch_name': actual_switch_name,
                'success': True,
                'inserted_count': inserted_count,
                'total_entries': len(switch_entries),
                'error': None
            }
            
        except Exception as e:
            error_msg = f"Error processing switch {actual_switch_name}: {str(e)}"
            logger.error(error_msg)
            
            # Update switch status with error
            try:
                switch_status = SwitchStatus.query.filter_by(switch_name=actual_switch_name).first()
                if switch_status:
                    switch_status.last_error = str(e)
                    switch_status.status = 'error'
                    db.session.commit()
            except Exception as status_error:
                logger.error(f"Failed to update switch status: {status_error}")
            
            return {
                'switch_name': actual_switch_name,
                'success': False,
                'inserted_count': 0,
                'total_entries': 0,
                'error': str(e)
            }

def run_simple_collection(username: str, password: str) -> Dict:
    """Final working collection with 4-switch parallel processing"""
    collection_id = str(uuid.uuid4())
    
    collection_run = CollectionRun(
        id=collection_id,
        status='running'
    )
    db.session.add(collection_run)
    db.session.commit()
    
    logger.info(f"Starting parallel collection run {collection_id}")
    
    # Refresh device_port.json at start of collection
    logger.info("Refreshing device_port.json from Docker container")
    refresh_device_port_data()
    
    try:
        switches = Config.load_switches()
        
        total_inserted = 0
        switches_processed = []
        
        # Determine optimal worker count based on available Gunicorn workers
        # If running in multi-worker mode, use available workers minus scheduler worker
        gunicorn_workers = int(os.getenv('GUNICORN_WORKERS', '1'))
        if gunicorn_workers > 1:
            # Reserve worker 0 for scheduler, use others for collections
            available_workers = gunicorn_workers - 1
            max_workers = min(available_workers, len(switches), 8)  # Cap at 8 for safety
            logger.info(f"Multi-worker mode: Using {max_workers} of {available_workers} available collection workers")
        else:
            # Single-worker mode: use ThreadPool as before
            max_workers = min(4, len(switches))
            logger.info(f"Single-worker mode: Using {max_workers} thread workers")
        
        logger.info(f"Processing {len(switches)} switches with {max_workers} parallel workers")
        
        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
            # Submit all switch processing tasks with app context
            future_to_switch = {
                executor.submit(process_single_switch, switch_info, username, password, collection_id, current_app._get_current_object()): switch_info
                for switch_info in switches
            }
            
            # Collect results as they complete
            for future in concurrent.futures.as_completed(future_to_switch):
                switch_info = future_to_switch[future]
                try:
                    result = future.result()
                    
                    if result['success']:
                        total_inserted += result['inserted_count']
                        switches_processed.append(result['switch_name'])
                        logger.info(f"✓ {result['switch_name']}: {result['inserted_count']} new entries")
                    else:
                        logger.error(f"✗ {result['switch_name']}: {result['error']}")
                        switches_processed.append(f"{result['switch_name']} (failed)")
                        
                except Exception as e:
                    parts = switch_info.split(':')
                    switch_name = parts[1] if len(parts) >= 2 else switch_info
                    logger.error(f"✗ {switch_name}: Thread execution failed: {str(e)}")
                    switches_processed.append(f"{switch_name} (failed)")
        
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
            'database_count': actual_count,
            'switch_names': switches_processed
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
