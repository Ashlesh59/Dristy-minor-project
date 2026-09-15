"""
CorporateAction Model — Represents official exchange corporate actions (splits, bonuses, dividends, etc.).
"""
from datetime import datetime
from database.db import db


class CorporateAction(db.Model):
    """
    Represents a corporate action announced by an issuer for a specific security.
    """
    __tablename__ = "corporate_actions"

    id = db.Column(db.Integer, primary_key=True)
    security_id = db.Column(
        db.Integer,
        db.ForeignKey("securities.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    action_type = db.Column(db.String(50), nullable=False, index=True)
    announcement_date = db.Column(db.Date, nullable=True)
    ex_date = db.Column(db.Date, nullable=False, index=True)
    record_date = db.Column(db.Date, nullable=True)
    action_description = db.Column(db.Text, nullable=False)
    ratio_from = db.Column(db.Numeric(14, 6), nullable=True)
    ratio_to = db.Column(db.Numeric(14, 6), nullable=True)
    cash_amount = db.Column(db.Numeric(14, 4), nullable=True)
    currency = db.Column(db.String(10), nullable=True, default="INR")
    source = db.Column(db.String(50), nullable=False, default="NSE_CA")
    source_event_key = db.Column(db.String(128), nullable=False)
    source_file_sha256 = db.Column(db.String(64), nullable=False)
    processing_status = db.Column(db.String(50), nullable=False, default="pending", index=True)
    review_reason = db.Column(db.String(255), nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    updated_at = db.Column(
        db.DateTime,
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )

    # Relationships
    security = db.relationship("Security", backref=db.backref("corporate_actions", lazy="dynamic", cascade="all, delete-orphan"))

    __table_args__ = (
        db.UniqueConstraint("source", "source_event_key", name="uq_corporate_actions_source_event_key"),
        db.Index("ix_corporate_actions_security_ex_date", "security_id", "ex_date"),
    )

    def __repr__(self):
        return (
            f"<CorporateAction id={self.id} security_id={self.security_id} "
            f"type='{self.action_type}' ex_date={self.ex_date} status='{self.processing_status}'>"
        )
