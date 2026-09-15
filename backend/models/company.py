"""
models/company.py
--------------------------------------------------------------------------
Company Model — Represents the corporate entity / business issuer.
--------------------------------------------------------------------------
"""

from datetime import datetime, timezone
from database.db import db


def _utc_now():
    return datetime.now(timezone.utc)


class Company(db.Model):
    __tablename__ = "companies"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    legal_name = db.Column(db.String(255), nullable=False)
    display_name = db.Column(db.String(255), nullable=False)
    normalized_name = db.Column(db.String(255), nullable=False, index=True)
    country = db.Column(db.String(10), nullable=False, default="IN", index=True)
    sector = db.Column(db.String(100), nullable=True)
    industry = db.Column(db.String(100), nullable=True)
    website = db.Column(db.String(255), nullable=True)
    is_active = db.Column(db.Boolean, nullable=False, default=True, index=True)
    created_at = db.Column(db.DateTime, nullable=False, default=_utc_now)
    updated_at = db.Column(db.DateTime, nullable=False, default=_utc_now, onupdate=_utc_now)

    # Relationship: One Company can issue multiple exchange-listed Securities
    securities = db.relationship(
        "Security",
        backref="company",
        cascade="all, delete-orphan",
        lazy=True,
    )

    def to_dict(self):
        return {
            "id": self.id,
            "legal_name": self.legal_name,
            "display_name": self.display_name,
            "normalized_name": self.normalized_name,
            "country": self.country,
            "sector": self.sector,
            "industry": self.industry,
            "website": self.website,
            "is_active": self.is_active,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "securities_count": len(self.securities) if self.securities else 0,
        }
