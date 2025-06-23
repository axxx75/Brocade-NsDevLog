#!/usr/bin/env python3
"""
Simple Switch Log Collector
Based on successful debug test that collected 2312 chars with real logs
"""

import paramiko
import time
import logging
import re
import json
import os
import uuid
from datetime import datetime
from typing import List, Dict, Optional

logger = logging.getLogger(__name__)


class SimpleLogCollector:
    """Simple collector that works exactly like the successful debug test"""

    def __init__(self, username: str, password: str):
        self.username = username
        self.password = password
        self.contexts = [1, 2, 3, 4, 5, 128]

        # Flexible regex pattern to capture ALL log entries with timestamps
        self.log_pattern = re.compile(
            r'^([A-Za-z]{3}\s+[A-Za-z]{3}\s+\d{2}\s+\d{2}:\d{2}:\d{2}\.\d{3})\s+'  # timestamp
            r'(\S+)\s+'           # slot/port or NA
            r'(\S+)\s+'           # PID or NA  
            r'(\S+)\s+'           # Port WWN or NA
            r'(\S+)\s+'           # Node WWN or NA
            r'(.+)$'              # event description
        )

    def connect_to_switch(self, switch_address: str) -> paramiko.SSHClient:
        """Connect to switch"""
        ssh_client = paramiko.SSHClient()
        ssh_client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

        import os
        connection_id = str(uuid.uuid4())[:8]
        logger.info(f"🔌 CONNECTION-{connection_id}: Connecting to {switch_address} (PID: {os.getpid()})")
        ssh_client.connect(hostname=switch_address,
                           username=self.username,
                           password=self.password,
                           timeout=30,
                           look_for_keys=False,
                           allow_agent=False)
        return ssh_client

    def collect_from_context_simple(self, ssh_client: paramiko.SSHClient,
                                    switch_name: str, context: int) -> str:
        """
        Collect logs using the EXACT approach that worked in debug test
        This collected 2312 chars with real logs vs 1164 chars of just table
        """
        try:
            logger.info(
                f"🎯 SIMPLE: Collecting from {switch_name} context {context}")

            # Create shell exactly like successful test
            shell = ssh_client.invoke_shell()
            time.sleep(2)

            # Clear buffer
            if shell.recv_ready():
                initial = shell.recv(1024).decode('utf-8', errors='ignore')
                logger.info(f"🧹 SIMPLE: Cleared {len(initial)} chars")

            # Send exact same command that worked
            cmd = f'fosexec --fid {context} -cmd "nsdevlog --show"'
            logger.info(f"📤 SIMPLE: Sending {cmd}")
            shell.send(f'{cmd}\n'.encode('utf-8'))

            # Smart completion detection - no fixed timeouts
            output = ""
            start_time = time.time()
            last_activity = start_time

            # Track completion indicators
            has_summary = False
            has_prompt = False
            command_complete = False

            logger.info(
                f"🧠 SMART: Waiting for command completion indicators...")

            while not command_complete:
                if shell.recv_ready():
                    chunk = shell.recv(8192).decode('utf-8', errors='ignore')
                    output += chunk
                    last_activity = time.time()
                    elapsed = time.time() - start_time

                    # Look for natural completion indicators
                    if 'Total number of' in chunk:
                        if not has_summary:
                            logger.info(
                                f"✅ Found log summary at {elapsed:.1f}s")
                            has_summary = True

                    # Look for Brocade switch prompt: NOME_SW_VIRT:FIDX:user>
                    lines_in_chunk = chunk.split('\n')
                    for line in lines_in_chunk:
                        line = line.strip()

                        # Brocade switch prompt is always FID128 (physical switch context)
                        # regardless of which virtual context we're querying
                        if ':FID128:' in line and line.endswith('>'):
                            if not has_prompt:
                                logger.info(f"✅ Physical switch prompt found at {elapsed:.1f}s: '{line}'")
                                has_prompt = True
                                break  # Found it, no need to check other lines

                    # Command is complete when we have both summary and prompt
                    if has_summary and has_prompt:
                        logger.info(f"🎯 Command completed at {elapsed:.1f}s")
                        command_complete = True
                        # Collect any remaining data
                        time.sleep(0.5)
                        while shell.recv_ready():
                            final_chunk = shell.recv(8192).decode(
                                'utf-8', errors='ignore')
                            output += final_chunk
                        break

                # Safety mechanism: if no activity for too long, break
                if time.time(
                ) - last_activity > 30:  # 30 seconds of inactivity
                    logger.warning(
                        f"⏰ No activity for 30s, assuming completion")
                    break

                # Absolute maximum safety (5 minutes)
                if time.time() - start_time > 300:
                    logger.warning(f"⏰ Maximum time reached (5min), stopping")
                    break

                time.sleep(0.1)  # Small polling interval

            has_logs = 'Total number of' in output or 'Device Add' in output
            logger.info(
                f"🎯 SIMPLE RESULT: {len(output)} chars, has_logs: {has_logs}")

            shell.close()
            return output

        except Exception as e:
            logger.error(f"❌ SIMPLE: Collection failed: {str(e)}")
            return ""







    def parse_log_line(self, line: str) -> Optional[Dict]:
        """Parse a log line into structured data"""
        line = line.strip()

        # Skip headers and empty lines
        if not line or line.startswith('=') or 'date/time' in line.lower():
            return None
        if 'total number' in line.lower() or 'max number' in line.lower():
            return None

        match = self.log_pattern.match(line)
        if not match:
            return None

        try:
            timestamp_str, slot_port, pid, port_wwn, node_wwn, event = match.groups(
            )
            return {
                'timestamp': timestamp_str.strip(),
                'slot_port': slot_port.strip(),
                'pid': pid.strip(),
                'port_wwn': port_wwn.strip(),
                'node_wwn': node_wwn.strip(),
                'event': event.strip(),
                'raw_line': line  # Add raw line for duplicate detection
            }
        except Exception:
            return None

    def parse_log_output_with_verification(self, raw_output: str, switch_name: str, context: int) -> List[Dict]:
        """
        Parse log output and verify entry count matches switch declaration
        """
        entries = []
        expected_count = None
        
        # Extract expected count from switch output
        lines = raw_output.split('\n')
        for line in lines:
            if 'Total number of Entries displayed' in line:
                try:
                    # Extract number from line like "Total number of Entries displayed = 14125"
                    expected_count = int(line.split('=')[1].strip())
                    break
                except:
                    pass
        
        # Parse actual entries
        for line in lines:
            parsed_entry = self.parse_log_line(line)
            if parsed_entry:
                # Add context and switch info
                parsed_entry['context'] = context
                parsed_entry['switch_name'] = switch_name
                entries.append(parsed_entry)
        
        # Verification
        actual_count = len(entries)
        if expected_count is not None:
            if actual_count == expected_count:
                logger.info(f"✅ VERIFY: Context {context} - {actual_count}/{expected_count} entries (100% match)")
            else:
                logger.warning(f"⚠️ VERIFY: Context {context} - {actual_count}/{expected_count} entries ({actual_count/expected_count*100:.1f}% match)")
                logger.warning(f"   Missing {expected_count - actual_count} entries - check parsing logic")
        else:
            logger.warning(f"❓ VERIFY: Context {context} - {actual_count} entries (no switch count found)")
        
        return entries

    def fix_timestamps_with_years(self, entries: List[Dict]) -> List[Dict]:
        """
        Intelligent year deduction: recent entries = current year, detect year boundaries going backward
        """
        if not entries:
            return entries

        current_year = datetime.now().year
        
        # Month name to number mapping
        month_names = {
            'Jan': 1, 'Feb': 2, 'Mar': 3, 'Apr': 4, 'May': 5, 'Jun': 6,
            'Jul': 7, 'Aug': 8, 'Sep': 9, 'Oct': 10, 'Nov': 11, 'Dec': 12
        }

        print(f"🗓️  Intelligent year deduction for {len(entries)} entries...")
        
        # Start from the end (most recent) and work backward
        assigned_year = current_year
        previous_month = None
        year_assignments = []
        
        # Process in reverse order (most recent first)
        for i, entry in enumerate(reversed(entries)):
            timestamp_str = entry.get('timestamp', '')
            if not timestamp_str:
                year_assignments.append(current_year)
                continue

            try:
                parts = timestamp_str.split()
                if len(parts) >= 4:
                    month_str = parts[1]
                    entry_month = month_names.get(month_str, 1)
                    
                    if i == 0:
                        # First entry (most recent) = current year
                        print(f"📅 Most recent: {timestamp_str} → {assigned_year}")
                    else:
                        # Check for year boundary: month increases going backward = previous year
                        if previous_month is not None and entry_month > previous_month:
                            assigned_year -= 1
                            print(f"📆 Year boundary: {month_str}({entry_month}) > prev({previous_month}) → {assigned_year}")
                    
                    previous_month = entry_month
                    year_assignments.append(assigned_year)
                else:
                    year_assignments.append(assigned_year)
                    
            except Exception as e:
                year_assignments.append(assigned_year)
                print(f"❌ Parse error: {timestamp_str}")

        # Reverse year assignments to match original entry order
        year_assignments.reverse()
        
        # Apply years to entries
        year_counts = {}
        for i, entry in enumerate(entries):
            assigned_year = year_assignments[i] if i < len(year_assignments) else current_year
            year_counts[assigned_year] = year_counts.get(assigned_year, 0) + 1
            
            timestamp_str = entry.get('timestamp', '')
            try:
                parts = timestamp_str.split()
                if len(parts) >= 4:
                    day_of_week = parts[0]
                    month = parts[1]
                    day = parts[2]
                    time_part = parts[3]
                    
                    full_timestamp = f"{day_of_week} {month} {day} {assigned_year} {time_part}"
                    entry['timestamp'] = full_timestamp
                    entry['deduced_year'] = assigned_year
                else:
                    entry['timestamp'] = f"{timestamp_str} {assigned_year}"
                    entry['deduced_year'] = assigned_year
            except:
                entry['timestamp'] = f"{timestamp_str} {assigned_year}"
                entry['deduced_year'] = assigned_year

        print(f"📊 Year deduction complete:")
        for year in sorted(year_counts.keys(), reverse=True):
            print(f"   {year}: {year_counts[year]} entries")

        return entries

    def collect_from_switch_simple(self, switch_info) -> List[Dict]:
        """
        Collect from all contexts of a switch using simple approach
        Returns all parsed log entries
        """
        all_entries = []

        try:
            # Parse string format "SITE:SWITCH:GEN"
            parts = switch_info.split(':')
            site = parts[0]
            switch_address = parts[1]
            generation = parts[2] if len(parts) > 2 else 'gen7'

            logger.info(
                f"🚀 SIMPLE: Starting collection from {site}:{switch_address} ({generation})"
            )

            # Connect
            ssh_client = self.connect_to_switch(switch_address)

            # Collect from each context
            for context in self.contexts:
                logger.info(f"📂 SIMPLE: Context {context}...")

                # Reset flags for each context
                if hasattr(self, '_found_summary'):
                    delattr(self, '_found_summary')
                if hasattr(self, '_found_device_events'):
                    delattr(self, '_found_device_events')

                raw_output = self.collect_from_context_simple(
                    ssh_client, switch_address, context)

                # Parse entries and verify count
                context_entries = self.parse_log_output_with_verification(raw_output, switch_address, context)
                logger.info(f"🔍 DEBUG: After parsing - {len(context_entries)} entries")
                
                # Add site info to entries
                for entry in context_entries:
                    entry['site'] = site
                
                # Fix timestamps with intelligent year assignment
                if context_entries:
                    original_count = len(context_entries)
                    context_entries = self.fix_timestamps_with_years(context_entries)
                    new_count = len(context_entries)
                    if original_count != new_count:
                        logger.warning(f"⚠️ DEBUG: Year assignment changed entry count from {original_count} to {new_count}")
                
                logger.info(f"🔍 DEBUG: Before extend - all_entries has {len(all_entries)}, adding {len(context_entries)}")
                all_entries.extend(context_entries)
                logger.info(f"🔍 DEBUG: After extend - all_entries has {len(all_entries)}")

                # Save temporary files for this context
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                context_filename = f"logs/context_{site}_{switch_address}_ctx{context}_{timestamp}.json"

                try:
                    os.makedirs('logs', exist_ok=True)

                    # Save log entries
                    with open(context_filename, 'w') as f:
                        json.dump(
                            {
                                'metadata': {
                                    'switch': switch_address,
                                    'site': site,
                                    'context': context,
                                    'generation': generation,
                                    'timestamp': timestamp,
                                    'total_entries': len(context_entries),
                                    'raw_output_length': len(raw_output)
                                },
                                'entries': context_entries
                            },
                            f,
                            indent=2)

                    logger.info(
                        f"💾 SIMPLE: Saved context file: {context_filename}")

                except Exception as save_error:
                    logger.error(
                        f"❌ Failed to save context file: {save_error}")

                logger.info(
                    f"✅ SIMPLE: Context {context}: {len(context_entries)} entries from {len(raw_output)} chars"
                )

                # Small delay between contexts
                time.sleep(1)

            ssh_client.close()
            logger.info(
                f"🎉 SIMPLE: Total collected from {switch_address}: {len(all_entries)} entries"
            )

            # Sort all entries by timestamp in descending order (newest first)
            if all_entries:
                all_entries.sort(
                    key=lambda entry: self._parse_timestamp_for_sort(
                        entry.get('timestamp', '')),
                    reverse=True)
                logger.info(
                    f"📊 SIMPLE: Sorted {len(all_entries)} entries by timestamp (newest first)"
                )

        except Exception as e:
            logger.error(
                f"❌ SIMPLE: Failed to collect from {switch_info}: {str(e)}")

        return all_entries

    def _parse_timestamp_for_sort(self, timestamp_str: str):
        """Parse timestamp for sorting, return datetime object"""
        try:
            # Handle different timestamp formats
            if not timestamp_str:
                return datetime.min

            # Try to parse "Wed Jun 28 2024 02:07:20.885" format
            from dateutil import parser
            return parser.parse(timestamp_str)
        except:
            # Return minimum date if parsing fails
            return datetime.min

