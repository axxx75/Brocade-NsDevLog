#!/usr/bin/env python3
"""
Configuration settings for Switch Log Analyzer
"""

import os

class Config:
    """Application configuration"""
    
    # Flask settings
    SECRET_KEY = os.getenv('SECRET_KEY', 'switch-analyzer-secret-key-change-in-production')
    
    # Default switch credentials (can be overridden in UI)
    DEFAULT_USERNAME = os.getenv('SWITCH_USERNAME', '')
    DEFAULT_PASSWORD = os.getenv('SWITCH_PASSWORD', '')
    
    # Switch configuration file
    SWITCHES_CONFIG_FILE = os.getenv('SWITCHES_CONFIG_FILE', 'switches.conf')
    
    @staticmethod
    def load_switches():
        """Load switch list from configuration file"""
        switches = []
        config_file = Config.SWITCHES_CONFIG_FILE
        
        try:
            if os.path.exists(config_file):
                with open(config_file, 'r') as f:
                    for line in f:
                        line = line.strip()
                        # Skip empty lines and comments
                        if line and not line.startswith('#'):
                            if ':' in line:
                                parts = line.split(':')
                                if len(parts) >= 2:
                                    site = parts[0].strip()
                                    switch = parts[1].strip()
                                    generation = parts[2].strip() if len(parts) > 2 else 'gen7'
                                    switches.append(f"{site}:{switch}:{generation}")
            else:
                # Default switches if config file doesn't exist
                default_switches = [
                    'ccm:ccmfcp2:gen6', 'ccm:santgtccm4:gen7', 'ccm:santgtccm6:gen7', 'ccm:santgtccm8:gen6',
                    'ccm:ccmfcp3:gen6', 'ccm:santgtccm5:gen7', 'ccm:santgtccm7:gen7', 'ccm:santgtccm9:gen6'
                ]
                switches.extend(default_switches)
                    
        except Exception as e:
            print(f"Error loading switches config: {e}")
            
        return switches

