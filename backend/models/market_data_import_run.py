"""
models/market_data_import_run.py
--------------------------------------------------------------------------
Audit log model for tracking End-of-Day Market Data batch import runs.
--------------------------------------------------------------------------
"""

import os
from datetime import datetime
from database.db import db


class MarketDataImportRun(db.Model):
    __tablename__ = "market_data_import_runs"

    id = db.Column(db.Integer, primary_key=True)
    source = db.Column(db.String(50), nullable=False)
    source_file = db.Column(db.String(255), nullable=False)  # Sanitized basename only
    file_sha256 = db.Column(db.String(64), nullable=False)
    trading_date = db.Column(db.Date, nullable=True)

    started_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    completed_at = db.Column(db.DateTime, nullable=True)
    status = db.Column(db.String(20), nullable=False)  # 'completed', 'failed', 'dry_run'

    total_rows = db.Column(db.Integer, nullable=False, default=0)
    inserted_rows = db.Column(db.Integer, nullable=False, default=0)
    updated_rows = db.Column(db.Integer, nullable=False, default=0)
    unchanged_rows = db.Column(db.Integer, nullable=False, default=0)
    skipped_rows = db.Column(db.Integer, nullable=False, default=0)
    unresolved_rows = db.Column(db.Integer, nullable=False, default=0)
    failed_rows = db.Column(db.Integer, nullable=False, default=0)
    error_summary = db.Column(db.Text, nullable=True)

    @classmethod
    def sanitize_path(cls, file_path):
        """Extracts only the basename of the file path to prevent exposing private system paths."""
        if not file_path:
            return "unknown_file"
        return os.path.basename(file_path)

    def to_dict(self):
        return {
            "id": self.id,
            "source": self.source,
            "source_file": self.source_file,
            "file_sha256": self.file_sha256,
            "trading_date": self.trading_date.isoformat() if self.trading_date else None,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "status": self.status,
            "total_rows": self.total_rows,
            "inserted_rows": self.inserted_rows,
            "updated_rows": self.updated_rows,
            "unchanged_rows": self.unchanged_rows,
            "skipped_rows": self.skipped_rows,
            "unresolved_rows": self.unresolved_rows,
            "failed_rows": self.failed_rows,
            "error_summary": self.error_summary,
        }
