"""
models/research.py
--------------------------------------------------------------------------
The Research model -- represents one row in the "research" table: a
single investment-research request a logged-in user has created.
--------------------------------------------------------------------------
"""

import json
from datetime import datetime, timezone
from database.db import db


def _utc_now():
    return datetime.now(timezone.utc)


class Research(db.Model):
    __tablename__ = "research"

    id = db.Column(db.Integer, primary_key=True)

    # Foreign key to users.id -- ties every research record to exactly one user
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)

    # Foreign keys to Company and Security (Phase 1B)
    company_id = db.Column(
        db.Integer,
        db.ForeignKey("companies.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    security_id = db.Column(
        db.Integer,
        db.ForeignKey("securities.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # Historical snapshot strings (kept for backward compatibility and archival)
    company_name = db.Column(db.String(200), nullable=False)
    ticker_symbol = db.Column(db.String(20), nullable=False)

    research_type = db.Column(db.String(50), nullable=False, default="general")
    status = db.Column(db.String(20), nullable=False, default="pending")

    created_at = db.Column(db.DateTime, default=_utc_now, nullable=False)
    updated_at = db.Column(db.DateTime, default=_utc_now, onupdate=_utc_now, nullable=False)

    # Persisted payload caches
    financial_data = db.Column(db.Text, nullable=True)
    news_data = db.Column(db.Text, nullable=True)
    analysis_data = db.Column(db.Text, nullable=True)
    report_data = db.Column(db.Text, nullable=True)
    ai_score = db.Column(db.Integer, nullable=True)
    recommendation = db.Column(db.String(50), nullable=True)

    # Relationships
    user = db.relationship("User", back_populates="research_records")
    company = db.relationship("Company", foreign_keys=[company_id], lazy=True)
    security = db.relationship("Security", foreign_keys=[security_id], lazy=True)

    @staticmethod
    def _load_json(text):
        if not text:
            return None
        try:
            return json.loads(text)
        except (ValueError, TypeError):
            return None

    def to_dict(self, include_details=True):
        sec_id = self.security_id
        if sec_id is None and self.ticker_symbol:
            try:
                from models.security import Security
                matched = Security.query.filter_by(symbol=self.ticker_symbol, is_active=True).first()
                if matched:
                    sec_id = matched.id
            except Exception:
                pass

        data = {
            "id": self.id,
            "user_id": self.user_id,
            "company_id": self.company_id,
            "security_id": sec_id,
            "company_name": self.company_name,
            "ticker_symbol": self.ticker_symbol,
            "research_type": self.research_type,
            "status": self.status,
            "ai_score": self.ai_score,
            "recommendation": self.recommendation,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
        if include_details:
            data["financial_data"] = self._load_json(self.financial_data)
            data["news_data"] = self._load_json(self.news_data)
            data["analysis_data"] = self._load_json(self.analysis_data)
            data["report_data"] = self._load_json(self.report_data)
            if self.company:
                data["company"] = self.company.to_dict()
            if self.security:
                data["security"] = self.security.to_dict()
        return data
