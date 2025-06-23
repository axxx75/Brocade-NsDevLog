#!/usr/bin/env python3
"""
Test script per verificare il funzionamento del sistema di cache device lookup
Crea dati di test e verifica le performance della cache LRU
"""

import json
import sqlite3
import os
import time
from device_lookup_optimized import DeviceLookupOptimized
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def create_test_device_data():
    """Crea dati di test realistici per verificare il cache"""
    test_data = []
    
    # Switches realistici
    switches = ['ccmfcp2', 'santgtccm4', 'santgtccm6', 'santgtccm7']
    
    # Genera dati test per ogni switch
    for switch in switches:
        for slot in range(1, 5):  # 4 slot per switch
            for port in range(1, 17):  # 16 porte per slot
                
                # WWN realistici (formato Brocade)
                wwn_base = f"20:00:00:25:b5:{slot:02x}:{port:02x}:0{switch[-1]}"
                physical_wwn = wwn_base
                
                # Device principale
                device = {
                    "pSwitch": switch,
                    "slotNumber": slot,
                    "portNumber": port,
                    "wwn": wwn_base,
                    "physicalPortWwn": physical_wwn,
                    "zoneAlias": f"HOST_{switch.upper()}_S{slot}P{port}",
                    "deviceSymbolicName": f"Server-{switch}-{slot}-{port}",
                    "symbolicName": f"Host-{switch}-Slot{slot}-Port{port}"
                }
                test_data.append(device)
                
                # Aggiungi alcuni dispositivi NPIV (virtual WWN)
                if port % 4 == 0:  # Ogni 4 porte
                    for npiv_id in range(1, 3):  # 2 NPIV per porta
                        npiv_wwn = f"21:00:00:25:b5:{slot:02x}:{port:02x}:{npiv_id:02x}"
                        npiv_device = {
                            "pSwitch": switch,
                            "slotNumber": slot,
                            "portNumber": port,
                            "wwn": npiv_wwn,
                            "physicalPortWwn": physical_wwn,  # Punta alla porta fisica
                            "zoneAlias": f"NPIV_{switch.upper()}_S{slot}P{port}_{npiv_id}",
                            "deviceSymbolicName": f"NPIV-{switch}-{slot}-{port}-{npiv_id}",
                            "symbolicName": f"Virtual-{switch}-Slot{slot}-Port{port}-{npiv_id}"
                        }
                        test_data.append(npiv_device)
    
    logger.info(f"Creati {len(test_data)} dispositivi di test")
    return test_data

def create_test_json_file(data):
    """Salva i dati di test in device_port.json"""
    with open('./device_port.json', 'w') as f:
        json.dump(data, f, indent=2)
    logger.info(f"Salvato device_port.json con {len(data)} entries")

def test_cache_performance():
    """Testa le performance della cache LRU"""
    
    # Crea istanza device lookup
    lookup = DeviceLookupOptimized()
    
    # Refresh index con i dati di test
    if not lookup.refresh_index():
        logger.error("Errore nel refresh dell'indice")
        return
    
    # Test queries ripetute per verificare cache
    test_queries = [
        ('ccmfcp2', 1, 1, '20:00:00:25:b5:01:01:02'),
        ('ccmfcp2', 1, 4, '21:00:00:25:b5:01:04:01'),  # NPIV
        ('santgtccm4', 2, 8, '20:00:00:25:b5:02:08:04'),
        ('santgtccm6', 3, 12, '21:00:00:25:b5:03:0c:02'),  # NPIV
        ('santgtccm7', 4, 16, '20:00:00:25:b5:04:10:07'),
    ]
    
    logger.info("\n=== Test Cache Performance ===")
    
    # Prima esecuzione (cache miss)
    logger.info("Prima esecuzione (dovrebbe essere cache miss):")
    start_time = time.time()
    
    for switch, slot, port, wwn in test_queries:
        alias, node_symbol = lookup.lookup_alias_and_node_symbol(switch, slot, port, wwn)
        logger.info(f"  {switch}:{slot}:{port}:{wwn} -> alias='{alias}', nodeSymbol='{node_symbol}'")
    
    first_run_time = time.time() - start_time
    logger.info(f"Tempo prima esecuzione: {first_run_time:.4f}s")
    
    # Mostra statistiche cache dopo prima esecuzione
    stats = lookup.get_statistics()
    cache_info = stats.get('cache_info', {})
    logger.info(f"Cache dopo prima esecuzione: hits={cache_info.get('hits', 0)}, misses={cache_info.get('misses', 0)}")
    
    # Seconda esecuzione (dovrebbe essere cache hit)
    logger.info("\nSeconda esecuzione (dovrebbe essere cache hit):")
    start_time = time.time()
    
    for switch, slot, port, wwn in test_queries:
        alias, node_symbol = lookup.lookup_alias_and_node_symbol(switch, slot, port, wwn)
        logger.info(f"  {switch}:{slot}:{port}:{wwn} -> alias='{alias}', nodeSymbol='{node_symbol}'")
    
    second_run_time = time.time() - start_time
    logger.info(f"Tempo seconda esecuzione: {second_run_time:.4f}s")
    
    # Statistiche finali
    stats = lookup.get_statistics()
    cache_info = stats.get('cache_info', {})
    
    logger.info(f"\n=== Statistiche Finali ===")
    logger.info(f"Dispositivi totali: {stats.get('total_devices', 0)}")
    logger.info(f"Dispositivi con alias: {stats.get('devices_with_alias', 0)}")
    logger.info(f"Dispositivi NPIV: {stats.get('npiv_devices', 0)}")
    logger.info(f"Cache hits: {cache_info.get('hits', 0)}")
    logger.info(f"Cache misses: {cache_info.get('misses', 0)}")
    
    if cache_info.get('hits', 0) > 0:
        hit_rate = cache_info.get('hits', 0) / (cache_info.get('hits', 0) + cache_info.get('misses', 0)) * 100
        logger.info(f"Cache hit rate: {hit_rate:.1f}%")
        logger.info(f"Speedup: {first_run_time/second_run_time:.1f}x più veloce")
    
    return stats

def test_npiv_logic():
    """Testa la logica NPIV"""
    lookup = DeviceLookupOptimized()
    
    logger.info("\n=== Test Logica NPIV ===")
    
    # Test WWN fisico
    alias, node_symbol = lookup.lookup_alias_and_node_symbol('ccmfcp2', 1, 4, '20:00:00:25:b5:01:04:02')
    logger.info(f"WWN Fisico: alias='{alias}', nodeSymbol='{node_symbol}'")
    
    # Test WWN virtuale NPIV (dovrebbe usare symbolicName della porta fisica)
    alias, node_symbol = lookup.lookup_alias_and_node_symbol('ccmfcp2', 1, 4, '21:00:00:25:b5:01:04:01')
    logger.info(f"WWN NPIV: alias='{alias}', nodeSymbol='{node_symbol}'")
    
    # Mostra esempi NPIV
    npiv_examples = lookup.get_npiv_examples(5)
    logger.info(f"\nEsempi NPIV trovati: {len(npiv_examples)}")
    for example in npiv_examples:
        logger.info(f"  Switch: {example['switch']}, NPIV: {example['npiv_wwn']}, Physical: {example['physical_wwn']}")

def verify_database_content():
    """Verifica il contenuto del database SQLite"""
    db_path = './device_lookup.db'
    
    if not os.path.exists(db_path):
        logger.error("Database SQLite non trovato")
        return
    
    try:
        with sqlite3.connect(db_path) as conn:
            cursor = conn.execute('SELECT COUNT(*) FROM device_ports')
            total = cursor.fetchone()[0]
            
            cursor = conn.execute('SELECT COUNT(*) FROM device_ports WHERE zoneAlias IS NOT NULL AND zoneAlias != ""')
            with_alias = cursor.fetchone()[0]
            
            cursor = conn.execute('SELECT COUNT(*) FROM device_ports WHERE physicalPortWwn != wwn')
            npiv_count = cursor.fetchone()[0]
            
            logger.info(f"\n=== Contenuto Database ===")
            logger.info(f"Dispositivi totali: {total}")
            logger.info(f"Con alias: {with_alias}")
            logger.info(f"Dispositivi NPIV: {npiv_count}")
            
            # Mostra alcuni esempi
            cursor = conn.execute('SELECT pSwitch, slotNumber, portNumber, wwn, zoneAlias LIMIT 5')
            logger.info("Esempi dispositivi:")
            for row in cursor.fetchall():
                logger.info(f"  {row[0]}:{row[1]}:{row[2]} {row[3]} -> {row[4]}")
                
    except Exception as e:
        logger.error(f"Errore verifica database: {e}")

if __name__ == "__main__":
    logger.info("=== Test Device Lookup Cache System ===")
    
    # 1. Crea dati di test
    test_data = create_test_device_data()
    create_test_json_file(test_data)
    
    # 2. Verifica contenuto database
    verify_database_content()
    
    # 3. Test performance cache
    test_cache_performance()
    
    # 4. Test logica NPIV
    test_npiv_logic()
    
    logger.info("\n=== Test Completato ===")
