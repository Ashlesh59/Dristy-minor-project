"""
AdjustmentRun Model — Audit log for historical price adjustment rebuild runs.
"""
from datetime import datetime
from database.db import db


class AdjustmentRun(db.Model):
    """
    Audit log tracking execution of split/bonus price adjustment calculation batches.
    """
    __tablename__ = "adjustment_runs"

    id = db.Column(db.Integer, primary_key=True)
    security_id = db.Column(
        db.Integer,
        db.ForeignKey("securities.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    adjustment_version = db.Column(db.String(50), nullable=False, default="split_bonus_v1", index=True)
    started_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    completed_at = db.Column(db.DateTime, nullable=True)
    status = db.Column(db.String(20), nullable=False, default="pending")  # pending, completed, failed, dry_run

    securities_processed = db.Column(db.Integer, nullable=False, default=0)
    prices_processed = db.Column(db.Integer, nullable=False, default=0)
    actions_applied = db.Column(db.Integer, nullable=False, default=0)
    manual_review_actions = db.Column(db.Integer, nullable=False, default=0)
    failed_securities = db.Column(db.Integer, nullable=False, default=0)
    error_summary = db.Column(db.Text, nullable=True)

    # Relationship
    security = db.relationship("Security", backref=db.backref("adjustment_runs", lazy="dynamic", cascade="all, delete-orphan"))

    def __repr__(self):
        return (
            f"<AdjustmentRun id={self.id} version='{self.adjustment_version}' "
            f"status='{self.status}' sec_count={self.securities_processed}>"
        )
