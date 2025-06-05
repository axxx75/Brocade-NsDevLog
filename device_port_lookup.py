#!/usr/bin/env python3
"""
Device Port Lookup Module
Handles alias and nodeSymbol lookup from device_port.json files using jq commands
"""
import json
import subprocess
import logging
import os
from typing import Optional, Dict, Tuple

logger = logging.getLogger(__name__)

def copy_device_port_json():
    """Copy device_port.json from Docker container"""
    try:
        cmd = [
            'docker', 'cp', 
            'sannav_app:/var/www/localhost/htdocs/result_json/device_port.json',
            './device_port.json'
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        
        if result.returncode == 0:
            logger.info("Successfully copied device_port.json from Docker container")
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

def lookup_alias_and_node_symbol(switch_name: str, slot_number: int, port_number: int, wwn: str) -> Tuple[Optional[str], Optional[str]]:
    """
    Lookup alias and nodeSymbol using jq commands on device_port.json
    
    Args:
        switch_name: Name of the switch (e.g., "ccmfcp2")
        slot_number: Slot number from log entry
        port_number: Port number from log entry  
        wwn: WWN from log entry
        
    Returns:
        Tuple of (alias, node_symbol) or (None, None) if not found
    """
    if not os.path.exists('./device_port.json'):
        logger.warning("device_port.json not found, attempting to copy from Docker")
        if not copy_device_port_json():
            return None, None
    
    try:
        # Format WWN to match device_port.json format (uppercase with colons)
        formatted_wwn = wwn.upper().replace('-', ':') if wwn else ""
        
        # Build jq filter for alias lookup
        alias_filter = f'.[]| select (.pSwitch == "{switch_name}" and .slotNumber == {slot_number} and .portNumber == {port_number} and .wwn == "{formatted_wwn}") | .zoneAlias'
        
        # Build jq filter for nodeSymbol lookup  
        node_symbol_filter = f'.[]| select (.pSwitch == "{switch_name}" and .slotNumber == {slot_number} and .portNumber == {port_number} and .wwn == "{formatted_wwn}") | .deviceSymbolicName'
        
        alias = None
        node_symbol = None
        
        # Lookup alias
        try:
            alias_cmd = ['cat', './device_port.json']
            jq_cmd = ['jq', '-r', alias_filter]
            
            cat_process = subprocess.Popen(alias_cmd, stdout=subprocess.PIPE)
            jq_process = subprocess.Popen(jq_cmd, stdin=cat_process.stdout, stdout=subprocess.PIPE, text=True)
            cat_process.stdout.close()
            
            alias_result, _ = jq_process.communicate(timeout=10)
            alias_result = alias_result.strip()
            
            if alias_result and alias_result != 'null' and alias_result != '':
                alias = alias_result
                
        except Exception as e:
            logger.debug(f"Alias lookup failed for {switch_name}:{slot_number}:{port_number}:{wwn}: {e}")
        
        # Lookup nodeSymbol
        try:
            node_cmd = ['cat', './device_port.json']
            jq_cmd = ['jq', '-r', node_symbol_filter]
            
            cat_process = subprocess.Popen(node_cmd, stdout=subprocess.PIPE)
            jq_process = subprocess.Popen(jq_cmd, stdin=cat_process.stdout, stdout=subprocess.PIPE, text=True)
            cat_process.stdout.close()
            
            node_result, _ = jq_process.communicate(timeout=10)
            node_result = node_result.strip()
            
            if node_result and node_result != 'null' and node_result != '':
                node_symbol = node_result
                
        except Exception as e:
            logger.debug(f"NodeSymbol lookup failed for {switch_name}:{slot_number}:{port_number}:{wwn}: {e}")
        
        if alias or node_symbol:
            logger.debug(f"Found lookup: {switch_name}:{slot_number}:{port_number}:{wwn} -> alias='{alias}', nodeSymbol='{node_symbol}'")
        
        return alias, node_symbol
        
    except Exception as e:
        logger.error(f"Error during lookup: {e}")
        return None, None

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

def refresh_device_port_data():
    """Refresh device_port.json from Docker container"""
    logger.info("Refreshing device_port.json from Docker container")
    return copy_device_port_json()
