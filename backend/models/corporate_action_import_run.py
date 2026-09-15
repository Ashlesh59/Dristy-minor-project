"""
CorporateActionImportRun Model — Audit log for corporate action batch import executions.
"""
from datetime import datetime
from database.db import db


class CorporateActionImportRun(db.Model):
    """
    Audit log tracking corporate actions batch import runs.
    """
    __tablename__ = "corporate_action_import_runs"

    id = db.Column(db.Integer, primary_key=True)
    source = db.Column(db.String(50), nullable=False, default="NSE_CA")
    source_file = db.Column(db.String(255), nullable=False)
    file_sha256 = db.Column(db.String(64), nullable=False, index=True)
    started_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    completed_at = db.Column(db.DateTime, nullable=True)
    status = db.Column(db.String(20), nullable=False, default="pending")  # pending, completed, failed, dry_run

    total_rows = db.Column(db.Integer, nullable=False, default=0)
    inserted_rows = db.Column(db.Integer, nullable=False, default=0)
    updated_rows = db.Column(db.Integer, nullable=False, default=0)
    unchanged_rows = db.Column(db.Integer, nullable=False, default=0)
    skipped_rows = db.Column(db.Integer, nullable=False, default=0)
    unresolved_rows = db.Column(db.Integer, nullable=False, default=0)
    manual_review_rows = db.Column(db.Integer, nullable=False, default=0)
    rejected_rows = db.Column(db.Integer, nullable=False, default=0)
    failed_rows = db.Column(db.Integer, nullable=False, default=0)
    error_summary = db.Column(db.Text, nullable=True)

    def __repr__(self):
        return (
            f"<CorporateActionImportRun id={self.id} source='{self.source}' "
            f"status='{self.status}' total={self.total_rows}>"
        )
