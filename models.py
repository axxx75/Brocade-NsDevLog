"""
Database Models for Switch Log Analyzer
PostgreSQL-based efficient log storage and management
"""

import os
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.orm import DeclarativeBase
from datetime import datetime
from sqlalchemy import Index


class Base(DeclarativeBase):
    pass


db = SQLAlchemy(model_class=Base)


class LogEntry(db.Model):
    """Main log entries table with optimized indexes"""
    __tablename__ = 'log_entries'
    
    id = db.Column(db.Integer, primary_key=True)
    
    # Core log data
    timestamp = db.Column(db.DateTime, nullable=False, index=True)
    switch_name = db.Column(db.String(100), nullable=False, index=True)
    context = db.Column(db.Integer, nullable=False, index=True)
    event_type = db.Column(db.String(50), nullable=True, index=True)
    
    # WWN and device information
    wwn = db.Column(db.String(30), nullable=True, index=True)
    port_info = db.Column(db.String(100), nullable=True)
    
    # Raw log line for reference
    raw_line = db.Column(db.Text, nullable=False)
    
    # Processed information
    alias = db.Column(db.String(200), nullable=True, index=True)
    node_symbol = db.Column(db.String(200), nullable=True, index=True)
    
    # Collection metadata
    collection_id = db.Column(db.String(36), nullable=False, index=True)  # UUID of collection run
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    
    def __init__(self, **kwargs):
        super(LogEntry, self).__init__(**kwargs)
    
    # Composite indexes for efficient queries
    __table_args__ = (
        Index('idx_timestamp_switch', 'timestamp', 'switch_name'),
        Index('idx_wwn_timestamp', 'wwn', 'timestamp'),
        Index('idx_collection_switch', 'collection_id', 'switch_name'),
        Index('idx_alias_search', 'alias'),
        Index('idx_node_symbol_search', 'node_symbol'),
    )
    
    def to_dict(self):
        """Convert to dictionary for API responses"""
        return {
            'id': self.id,
            'timestamp': self.timestamp.isoformat() if self.timestamp else None,
            'switch_name': self.switch_name,
            'context': self.context,
            'event_type': self.event_type,
            'wwn': self.wwn,
            'port_info': self.port_info,
            'raw_line': self.raw_line,
            'alias': self.alias,
            'node_symbol': self.node_symbol,
            'collection_id': self.collection_id,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }


class CollectionRun(db.Model):
    """Track collection runs and their metadata"""
    __tablename__ = 'collection_runs'
    
    id = db.Column(db.String(36), primary_key=True)  # UUID
    started_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    completed_at = db.Column(db.DateTime, nullable=True)
    status = db.Column(db.String(20), default='running', nullable=False)  # running, completed, failed
    
    # Collection parameters
    switches_processed = db.Column(db.JSON, nullable=True)  # List of switches
    total_entries = db.Column(db.Integer, default=0)
    new_entries = db.Column(db.Integer, default=0)
    
    # Time range for collection
    collect_from_date = db.Column(db.DateTime, nullable=True)  # Only collect entries after this date
    collect_to_date = db.Column(db.DateTime, nullable=True)
    
    # Error information
    error_message = db.Column(db.Text, nullable=True)
    
    def __init__(self, **kwargs):
        super(CollectionRun, self).__init__(**kwargs)
    
    def to_dict(self):
        """Convert to dictionary for API responses"""
        return {
            'id': self.id,
            'started_at': self.started_at.isoformat() if self.started_at else None,
            'completed_at': self.completed_at.isoformat() if self.completed_at else None,
            'status': self.status,
            'switches_processed': self.switches_processed,
            'total_entries': self.total_entries,
            'new_entries': self.new_entries,
            'collect_from_date': self.collect_from_date.isoformat() if self.collect_from_date else None,
            'collect_to_date': self.collect_to_date.isoformat() if self.collect_to_date else None,
            'error_message': self.error_message
        }


class AliasMapping(db.Model):
    """Alias mappings from CSV file"""
    __tablename__ = 'alias_mappings'
    
    id = db.Column(db.Integer, primary_key=True)
    wwn = db.Column(db.String(20), nullable=False, unique=True, index=True)
    alias = db.Column(db.String(200), nullable=False, index=True)
    node_symbol = db.Column(db.String(200), nullable=True, index=True)
    
    # Metadata
    source_file = db.Column(db.String(255), nullable=True)  # Which CSV file
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    
    def to_dict(self):
        """Convert to dictionary for API responses"""
        return {
            'id': self.id,
            'wwn': self.wwn,
            'alias': self.alias,
            'node_symbol': self.node_symbol,
            'source_file': self.source_file,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None
        }


class SwitchStatus(db.Model):
    """Track last successful collection from each switch"""
    __tablename__ = 'switch_status'
    
    id = db.Column(db.Integer, primary_key=True)
    switch_name = db.Column(db.String(100), nullable=False, unique=True, index=True)
    last_collection_date = db.Column(db.DateTime, nullable=False)
    last_collection_id = db.Column(db.String(36), nullable=False)
    last_entry_count = db.Column(db.Integer, default=0)
    status = db.Column(db.String(20), default='active', nullable=False)  # active, error, disabled
    last_error = db.Column(db.Text, nullable=True)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    
    def __init__(self, **kwargs):
        super(SwitchStatus, self).__init__(**kwargs)
    
    def to_dict(self):
        """Convert to dictionary for API responses"""
        return {
            'id': self.id,
            'switch_name': self.switch_name,
            'last_collection_date': self.last_collection_date.isoformat() if self.last_collection_date else None,
            'last_collection_id': self.last_collection_id,
            'last_entry_count': self.last_entry_count,
            'status': self.status,
            'last_error': self.last_error,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None
        }


class AppConfig(db.Model):
    """Application configuration stored in database"""
    __tablename__ = 'app_config'
    
    id = db.Column(db.Integer, primary_key=True)
    config_key = db.Column(db.String(100), nullable=False, unique=True, index=True)
    config_value = db.Column(db.Text, nullable=True)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    
    def __init__(self, **kwargs):
        super(AppConfig, self).__init__(**kwargs)
    
    @staticmethod
    def get_value(key, default=None):
        """Get configuration value"""
        config = AppConfig.query.filter_by(config_key=key).first()
        if config:
            try:
                import json
                return json.loads(config.config_value)
            except:
                return config.config_value
        return default
    
    @staticmethod
    def set_value(key, value):
        """Set configuration value"""
        try:
            import json
            value_str = json.dumps(value) if not isinstance(value, str) else value
            
            config = AppConfig.query.filter_by(config_key=key).first()
            if config:
                config.config_value = value_str
                config.updated_at = datetime.utcnow()
            else:
                config = AppConfig()
                config.config_key = key
                config.config_value = value_str
                db.session.add(config)
            
            db.session.commit()
            return True
        except Exception as e:
            db.session.rollback()
            return False


class ScheduledJob(db.Model):
    """Persistent storage for scheduled jobs"""
    __tablename__ = 'scheduled_jobs'
    
    id = db.Column(db.String(100), primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    cron_expression = db.Column(db.String(100), nullable=False)
    username = db.Column(db.String(100), nullable=False)
    password = db.Column(db.String(100), nullable=False)  # Should be encrypted in production
    enabled = db.Column(db.Boolean, default=True, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    last_run = db.Column(db.DateTime, nullable=True)
    next_run = db.Column(db.DateTime, nullable=True)
    
    def __init__(self, **kwargs):
        if 'updated_at' not in kwargs:
            kwargs['updated_at'] = datetime.utcnow()
        super().__init__(**kwargs)
    
    def to_dict(self):
        """Convert to dictionary for API responses"""
        return {
            'id': self.id,
            'name': self.name,
            'cron_expression': self.cron_expression,
            'enabled': self.enabled,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
            'last_run': self.last_run.isoformat() if self.last_run else None,
            'next_run': self.next_run.isoformat() if self.next_run else None
        }
