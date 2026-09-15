"""
models/data_import_run.py
--------------------------------------------------------------------------
DataImportRun Model — Audit log and execution statistics for data imports.
--------------------------------------------------------------------------
"""

from datetime import datetime, timezone
from database.db import db


def _utc_now():
    return datetime.now(timezone.utc)


class DataImportRun(db.Model):
    __tablename__ = "data_import_runs"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    source = db.Column(db.String(100), nullable=False)
    source_file = db.Column(db.String(255), nullable=False)
    file_sha256 = db.Column(db.String(64), nullable=False)
    started_at = db.Column(db.DateTime, nullable=False, default=_utc_now)
    completed_at = db.Column(db.DateTime, nullable=True)
    status = db.Column(db.String(50), nullable=False, default="pending")  # pending, completed, failed, dry_run
    total_rows = db.Column(db.Integer, default=0)
    inserted_companies = db.Column(db.Integer, default=0)
    updated_companies = db.Column(db.Integer, default=0)
    inserted_securities = db.Column(db.Integer, default=0)
    updated_securities = db.Column(db.Integer, default=0)
    unchanged_securities = db.Column(db.Integer, default=0)
    skipped_rows = db.Column(db.Integer, default=0)
    failed_rows = db.Column(db.Integer, default=0)
    deactivated_securities = db.Column(db.Integer, default=0)
    error_summary = db.Column(db.Text, nullable=True)

    def to_dict(self):
        return {
            "id": self.id,
            "source": self.source,
            "source_file": self.source_file,
            "file_sha256": self.file_sha256,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "status": self.status,
            "total_rows": self.total_rows,
            "inserted_companies": self.inserted_companies,
            "updated_companies": self.updated_companies,
            "inserted_securities": self.inserted_securities,
            "updated_securities": self.updated_securities,
            "unchanged_securities": self.unchanged_securities,
            "skipped_rows": self.skipped_rows,
            "failed_rows": self.failed_rows,
            "deactivated_securities": self.deactivated_securities,
            "error_summary": self.error_summary,
        }
