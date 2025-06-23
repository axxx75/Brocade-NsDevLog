#!/usr/bin/env python3
"""
Optimized Device Port Lookup Module
Uses SQLite indexing and LRU cache for fast alias and nodeSymbol lookups
"""
import json
import sqlite3
import subprocess
import logging
import os
import mmap
from typing import Optional, Dict, Tuple
from functools import lru_cache
import threading
from datetime import datetime

logger = logging.getLogger(__name__)

class DeviceLookupOptimized:
    """Optimized device lookup with SQLite indexing and LRU cache"""
    
    def __init__(self, db_path: str = './device_lookup.db'):
        self.db_path = db_path
        self.json_file = './device_port.json'
        self.lock = threading.Lock()
        self._initialize_database()
    
    def _initialize_database(self):
        """Initialize SQLite database with proper indexes"""
        with sqlite3.connect(self.db_path) as conn:
            # Check if table exists and get its schema
            cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='device_ports'")
            table_exists = cursor.fetchone() is not None
            
            if table_exists:
                # Check if symbolicName column exists
                cursor = conn.execute("PRAGMA table_info(device_ports)")
                columns = [row[1] for row in cursor.fetchall()]
                
                if 'symbolicName' not in columns:
                    # Add symbolicName column if it doesn't exist
                    conn.execute('ALTER TABLE device_ports ADD COLUMN symbolicName TEXT')
                    logger.info("Added symbolicName column to existing table")
                    
                    # Migrate data from deviceSymbolicName to symbolicName if needed
                    if 'deviceSymbolicName' in columns:
                        conn.execute('UPDATE device_ports SET symbolicName = deviceSymbolicName WHERE symbolicName IS NULL')
                        logger.info("Migrated data from deviceSymbolicName to symbolicName")
                
                if 'physicalPortWwn' not in columns:
                    # Add physicalPortWwn column for NPIV support
                    conn.execute('ALTER TABLE device_ports ADD COLUMN physicalPortWwn TEXT')
                    logger.info("Added physicalPortWwn column for NPIV support")
            else:
                # Create new table with both columns for compatibility
                conn.execute('''
                    CREATE TABLE device_ports (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        pSwitch TEXT NOT NULL,
                        slotNumber INTEGER NOT NULL,
                        portNumber INTEGER NOT NULL,
                        wwn TEXT NOT NULL,
                        physicalPortWwn TEXT,
                        zoneAlias TEXT,
                        deviceSymbolicName TEXT,
                        symbolicName TEXT,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                ''')
            
            # Create composite index for fast lookups
            conn.execute('''
                CREATE UNIQUE INDEX IF NOT EXISTS idx_device_lookup 
                ON device_ports (pSwitch, slotNumber, portNumber, wwn)
            ''')
            
            # Create separate indexes for partial lookups
            conn.execute('''
                CREATE INDEX IF NOT EXISTS idx_switch_wwn 
                ON device_ports (pSwitch, wwn)
            ''')
            
            conn.execute('''
                CREATE INDEX IF NOT EXISTS idx_zone_alias 
                ON device_ports (zoneAlias)
            ''')
            
            conn.commit()
            logger.info("Device lookup database initialized with indexes")
    
    def copy_device_port_json(self) -> bool:
        """Copy device_port.json from Docker container"""
        try:
            # Add detailed debug logging
            logger.info("Attempting to copy device_port.json from Docker container...")
            
            # Check if docker command exists
            import shutil
            docker_path = shutil.which('docker')
            
            if not docker_path:
                logger.error("Docker command not found in PATH")
                return False
            
            logger.info(f"Found docker at: {docker_path}")
            
            # Check if container exists with fallback for Docker/Podman conflicts
            check_cmd = ['docker', 'ps', '-a', '--format', '{{.Names}}']
            check_result = subprocess.run(check_cmd, capture_output=True, text=True, timeout=10)
            
            if check_result.returncode != 0:
                # Check for specific Podman database permission error
                if "read-only file system" in check_result.stderr and "libpod" in check_result.stderr:
                    logger.warning("Docker/Podman conflict detected - attempting direct container access")
                    # Skip container listing and proceed directly to copy attempt
                    logger.info("Bypassing container listing due to Docker/Podman database conflict")
                else:
                    logger.error(f"Failed to list containers: {check_result.stderr}")
                    return False
            else:
                containers = check_result.stdout.strip().split('\n')
                logger.info(f"Available containers: {containers}")
                
                if 'sannav_app' not in containers:
                    logger.error("Container 'sannav_app' not found in available containers")
                    return False
                
                logger.info("Container 'sannav_app' found")
            
            # Check if container is running (skip if we bypassed listing)
            if check_result.returncode == 0:
                running_cmd = ['docker', 'ps', '--format', '{{.Names}}']
                running_result = subprocess.run(running_cmd, capture_output=True, text=True, timeout=10)
                
                if running_result.returncode == 0:
                    running_containers = running_result.stdout.strip().split('\n')
                    logger.info(f"Running containers: {running_containers}")
                    
                    if 'sannav_app' not in running_containers:
                        logger.warning("Container 'sannav_app' is not running")
                    else:
                        logger.info("Container 'sannav_app' is running")
                else:
                    logger.warning("Could not check running containers, proceeding with copy attempt")
            else:
                logger.info("Skipping running check due to Docker/Podman conflict")
            
            # Check if source file exists in container
            file_check_cmd = ['docker', 'exec', 'sannav_app', 'ls', '-la', '/var/www/localhost/htdocs/result_json/device_port.json']
            file_check_result = subprocess.run(file_check_cmd, capture_output=True, text=True, timeout=10)
            
            if file_check_result.returncode == 0:
                logger.info(f"Source file exists in container: {file_check_result.stdout.strip()}")
            else:
                # Check for Docker/Podman database conflict in exec command too
                if "read-only file system" in file_check_result.stderr and "libpod" in file_check_result.stderr:
                    logger.warning("Docker exec also blocked by Podman database conflict - trying native podman")
                    # Try using podman directly if available
                    try:
                        podman_check = subprocess.run(['podman', 'exec', 'sannav_app', 'ls', '-la', '/var/www/localhost/htdocs/result_json/device_port.json'], 
                                                    capture_output=True, text=True, timeout=10)
                        if podman_check.returncode == 0:
                            logger.info(f"Source file exists via podman: {podman_check.stdout.strip()}")
                            # Use podman for the copy operation
                            cmd = [
                                'podman', 'cp', 
                                'sannav_app:/var/www/localhost/htdocs/result_json/device_port.json',
                                self.json_file
                            ]
                            logger.info(f"Using podman for copy: {' '.join(cmd)}")
                        else:
                            logger.error(f"Podman exec also failed: {podman_check.stderr}")
                            return False
                    except FileNotFoundError:
                        logger.error("Neither docker nor podman commands work - container access impossible")
                        return False
                else:
                    logger.error(f"Source file not found in container: {file_check_result.stderr}")
                    return False
            
            # Attempt the copy (cmd may be set to podman from file check above)
            cmd = [
                'docker', 'cp', 
                'sannav_app:/var/www/localhost/htdocs/result_json/device_port.json',
                self.json_file
            ]
            
            logger.info(f"Executing command: {' '.join(cmd)}")
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            
            # If docker copy fails with Podman conflict, try podman directly
            if result.returncode != 0 and "read-only file system" in result.stderr and "libpod" in result.stderr:
                logger.warning("Docker copy failed with Podman conflict - trying podman directly")
                try:
                    podman_cmd = [
                        'podman', 'cp', 
                        'sannav_app:/var/www/localhost/htdocs/result_json/device_port.json',
                        self.json_file
                    ]
                    logger.info(f"Fallback command: {' '.join(podman_cmd)}")
                    result = subprocess.run(podman_cmd, capture_output=True, text=True, timeout=30)
                except FileNotFoundError:
                    logger.error("Podman command not available for fallback")
                    return False
            
            logger.info(f"Command exit code: {result.returncode}")
            if result.stdout:
                logger.info(f"Command stdout: {result.stdout}")
            if result.stderr:
                logger.error(f"Command stderr: {result.stderr}")
            
            if result.returncode == 0:
                logger.info("Successfully copied device_port.json from Docker container")
                # Verify the copied file
                if os.path.exists(self.json_file):
                    file_size = os.path.getsize(self.json_file)
                    logger.info(f"Copied file size: {file_size} bytes")
                return True
            else:
                logger.error(f"Failed to copy device_port.json: {result.stderr}")
                return False
                
        except subprocess.TimeoutExpired:
            logger.error("Timeout while copying device_port.json")
            return False
        except Exception as e:
            logger.error(f"Error copying device_port.json: {e}")
            return False
    
    def _get_json_modification_time(self) -> Optional[float]:
        """Get JSON file modification time"""
        try:
            if os.path.exists(self.json_file):
                return os.path.getmtime(self.json_file)
        except Exception as e:
            logger.error(f"Error getting JSON modification time: {e}")
        return None
    
    def _get_db_last_update(self) -> Optional[float]:
        """Get database last update timestamp"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.execute('''
                    SELECT MAX(created_at) FROM device_ports
                ''')
                result = cursor.fetchone()[0]
                if result:
                    dt = datetime.fromisoformat(result.replace('Z', '+00:00'))
                    return dt.timestamp()
        except Exception as e:
            logger.debug(f"Error getting DB last update: {e}")
        return None
    
    def _needs_reindex(self) -> bool:
        """Check if reindexing is needed"""
        json_time = self._get_json_modification_time()
        db_time = self._get_db_last_update()
        
        if not json_time:
            return True
        if not db_time:
            return True
        
        return json_time > db_time
    
    def _stream_json_processing(self):
        """Process JSON file in streaming mode with memory mapping"""
        try:
            with open(self.json_file, 'rb') as f:
                with mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ) as mm:
                    data = json.loads(mm.read())
                    
            if not isinstance(data, list):
                logger.error("JSON data is not a list")
                return []
            
            logger.info(f"Loaded {len(data)} records from JSON")
            return data
            
        except Exception as e:
            logger.error(f"Error processing JSON: {e}")
            return []
    
    def _batch_insert_devices(self, devices: list, batch_size: int = 1000):
        """Insert devices in batches for better performance"""
        with sqlite3.connect(self.db_path) as conn:
            # Clear existing data
            conn.execute('DELETE FROM device_ports')
            
            for i in range(0, len(devices), batch_size):
                batch = devices[i:i + batch_size]
                records = []
                
                for device in batch:
                    try:
                        # Get both symbolic name fields for compatibility
                        device_symbolic_name = device.get('deviceSymbolicName', '')
                        symbolic_name = device.get('symbolicName') or device_symbolic_name
                        physical_port_wwn = device.get('physicalPortWwn', '')
                        
                        record = (
                            device.get('pSwitch', ''),
                            int(device.get('slotNumber', 0)),
                            int(device.get('portNumber', 0)),
                            device.get('wwn', ''),
                            physical_port_wwn,
                            device.get('zoneAlias', ''),
                            device_symbolic_name,
                            symbolic_name
                        )
                        records.append(record)
                    except (ValueError, TypeError) as e:
                        logger.debug(f"Skipping invalid device record: {e}")
                        continue
                
                if records:
                    conn.executemany('''
                        INSERT OR REPLACE INTO device_ports 
                        (pSwitch, slotNumber, portNumber, wwn, physicalPortWwn, zoneAlias, deviceSymbolicName, symbolicName)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    ''', records)
                
                logger.info(f"Inserted batch {i//batch_size + 1}: {len(records)} records")
            
            conn.commit()
            
            # Get final count
            cursor = conn.execute('SELECT COUNT(*) FROM device_ports')
            total_count = cursor.fetchone()[0]
            logger.info(f"Successfully indexed {total_count} device records")
    
    def refresh_index(self) -> bool:
        """Refresh the device lookup index"""
        with self.lock:
            try:
                # Copy fresh JSON file
                if not self.copy_device_port_json():
                    logger.warning("Failed to copy JSON, using existing file if available")
                
                if not os.path.exists(self.json_file):
                    logger.error("No device_port.json file available")
                    return False
                
                # Check if reindexing is needed
                if not self._needs_reindex():
                    logger.info("Device index is up to date")
                    return True
                
                logger.info("Starting device lookup index refresh...")
                
                # Process JSON file
                devices = self._stream_json_processing()
                if not devices:
                    logger.error("No valid device data found")
                    return False
                
                # Batch insert into SQLite
                self._batch_insert_devices(devices)
                
                # Clear LRU cache
                self.lookup_alias_and_node_symbol.cache_clear()
                
                logger.info("Device lookup index refresh completed")
                return True
                
            except Exception as e:
                logger.error(f"Error refreshing device index: {e}")
                return False
    
    @lru_cache(maxsize=10000)
    def lookup_alias_and_node_symbol(self, switch_name: str, slot_number: int, port_number: int, wwn: str) -> Tuple[Optional[str], Optional[str]]:
        """
        Fast lookup using SQLite index with LRU cache and NPIV intelligence
        
        For NPIV devices (where WWN != physicalPortWwn), returns the symbolicName 
        of the physical port instead of the virtual port.
        
        Args:
            switch_name: Name of the switch (e.g., "ccmfcp2")
            slot_number: Slot number from log entry
            port_number: Port number from log entry  
            wwn: WWN from log entry
            
        Returns:
            Tuple of (alias, node_symbol) or (None, None) if not found
        """
        try:
            # Format WWN to match device_port.json format (uppercase with colons)
            formatted_wwn = wwn.upper().replace('-', ':') if wwn else ""
            
            with sqlite3.connect(self.db_path) as conn:
                # First, get the device record for this WWN
                cursor = conn.execute('''
                    SELECT zoneAlias, COALESCE(symbolicName, deviceSymbolicName) as nodeSymbol, 
                           physicalPortWwn, wwn
                    FROM device_ports 
                    WHERE pSwitch = ? AND slotNumber = ? AND portNumber = ? AND wwn = ?
                    LIMIT 1
                ''', (switch_name, slot_number, port_number, formatted_wwn))
                
                result = cursor.fetchone()
                
                if result:
                    alias = result[0] if result[0] and result[0].strip() else None
                    node_symbol = result[1] if result[1] and result[1].strip() else None
                    physical_port_wwn = result[2] if result[2] and result[2].strip() else None
                    current_wwn = result[3] if result[3] and result[3].strip() else None
                    
                    # NPIV Intelligence: If this is an NPIV device (WWN != physicalPortWwn)
                    # and we have a physicalPortWwn, look up the physical port's symbolicName
                    if (physical_port_wwn and current_wwn and 
                        physical_port_wwn.upper() != current_wwn.upper()):
                        
                        logger.debug(f"NPIV detected: {current_wwn} has physical port {physical_port_wwn}")
                        
                        # Look up the physical port's symbolicName
                        physical_cursor = conn.execute('''
                            SELECT COALESCE(symbolicName, deviceSymbolicName) as physicalNodeSymbol
                            FROM device_ports 
                            WHERE pSwitch = ? AND slotNumber = ? AND portNumber = ? AND wwn = ?
                            LIMIT 1
                        ''', (switch_name, slot_number, port_number, physical_port_wwn))
                        
                        physical_result = physical_cursor.fetchone()
                        
                        if physical_result and physical_result[0] and physical_result[0].strip():
                            physical_node_symbol = physical_result[0].strip()
                            logger.debug(f"Using physical port symbolicName: {physical_node_symbol} for NPIV {current_wwn}")
                            node_symbol = physical_node_symbol
                    
                    if alias or node_symbol:
                        logger.debug(f"Found lookup: {switch_name}:{slot_number}:{port_number}:{wwn} -> alias='{alias}', nodeSymbol='{node_symbol}'")
                    
                    return alias, node_symbol
                
                return None, None
                
        except Exception as e:
            logger.error(f"Error during lookup: {e}")
            return None, None
    
    def get_statistics(self) -> Dict:
        """Get lookup database statistics"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.execute('SELECT COUNT(*) FROM device_ports')
                total_devices = cursor.fetchone()[0]
                
                cursor = conn.execute('SELECT COUNT(*) FROM device_ports WHERE zoneAlias IS NOT NULL AND zoneAlias != ""')
                devices_with_alias = cursor.fetchone()[0]
                
                cursor = conn.execute('SELECT COUNT(*) FROM device_ports WHERE deviceSymbolicName IS NOT NULL AND deviceSymbolicName != ""')
                devices_with_node_symbol = cursor.fetchone()[0]
                
                cursor = conn.execute('SELECT COUNT(DISTINCT pSwitch) FROM device_ports')
                unique_switches = cursor.fetchone()[0]
                
                # NPIV statistics
                cursor = conn.execute('SELECT COUNT(*) FROM device_ports WHERE physicalPortWwn IS NOT NULL AND physicalPortWwn != ""')
                devices_with_physical_wwn = cursor.fetchone()[0]
                
                cursor = conn.execute('SELECT COUNT(*) FROM device_ports WHERE physicalPortWwn IS NOT NULL AND physicalPortWwn != "" AND physicalPortWwn != wwn')
                npiv_devices = cursor.fetchone()[0]
                
                return {
                    'total_devices': total_devices,
                    'devices_with_alias': devices_with_alias,
                    'devices_with_node_symbol': devices_with_node_symbol,
                    'unique_switches': unique_switches,
                    'devices_with_physical_wwn': devices_with_physical_wwn,
                    'npiv_devices': npiv_devices,
                    'cache_info': self.lookup_alias_and_node_symbol.cache_info()._asdict()
                }
                
        except Exception as e:
            logger.error(f"Error getting lookup statistics: {e}")
            return {
                'total_devices': 0,
                'devices_with_alias': 0,
                'devices_with_node_symbol': 0,
                'unique_switches': 0,
                'devices_with_physical_wwn': 0,
                'npiv_devices': 0,
                'cache_info': {}
            }

    def get_npiv_examples(self, limit: int = 10) -> list:
        """Get examples of NPIV devices for demonstration"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.execute('''
                    SELECT pSwitch, slotNumber, portNumber, wwn, physicalPortWwn,
                           COALESCE(symbolicName, deviceSymbolicName) as nodeSymbol,
                           zoneAlias
                    FROM device_ports 
                    WHERE physicalPortWwn IS NOT NULL 
                      AND physicalPortWwn != "" 
                      AND physicalPortWwn != wwn
                    LIMIT ?
                ''', (limit,))
                
                results = []
                for row in cursor.fetchall():
                    results.append({
                        'switch': row[0],
                        'slot': row[1],
                        'port': row[2],
                        'npiv_wwn': row[3],
                        'physical_wwn': row[4],
                        'node_symbol': row[5],
                        'alias': row[6]
                    })
                
                return results
                
        except Exception as e:
            logger.error(f"Error getting NPIV examples: {e}")
            return []

# Global instance
device_lookup = DeviceLookupOptimized()

def extract_slot_port_from_entry(entry: Dict) -> Tuple[Optional[int], Optional[int]]:
    """
    Extract slot and port numbers from log entry
    
    Args:
        entry: Log entry dictionary
        
    Returns:
        Tuple of (slot_number, port_number) or (None, None) if not extractable
    """
    try:
        # Try to extract from port_info field (e.g., "2/14")
        port_info = entry.get('port_info', '')
        if '/' in port_info:
            parts = port_info.split('/')
            if len(parts) >= 2:
                slot_number = int(parts[0])
                port_number = int(parts[1])
                return slot_number, port_number
        
        # Try to extract from slot_port field
        slot_port = entry.get('slot_port', '')
        if '/' in slot_port:
            parts = slot_port.split('/')
            if len(parts) >= 2:
                slot_number = int(parts[0])
                port_number = int(parts[1])
                return slot_number, port_number
                
        # Try individual fields
        slot_number = entry.get('slot_number')
        port_number = entry.get('port_number')
        
        if slot_number is not None and port_number is not None:
            return int(slot_number), int(port_number)
            
        return None, None
        
    except (ValueError, TypeError) as e:
        logger.debug(f"Failed to extract slot/port from entry: {e}")
        return None, None

def lookup_alias_and_node_symbol(switch_name: str, slot_number: int, port_number: int, wwn: str) -> Tuple[Optional[str], Optional[str]]:
    """Wrapper function for compatibility"""
    return device_lookup.lookup_alias_and_node_symbol(switch_name, slot_number, port_number, wwn)

def refresh_device_port_data() -> bool:
    """Refresh device port data from Docker container"""
    return device_lookup.refresh_index()
