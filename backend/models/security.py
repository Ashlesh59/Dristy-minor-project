"""
models/security.py
--------------------------------------------------------------------------
Security Model — Represents an exchange-listed financial instrument.
--------------------------------------------------------------------------
"""

from datetime import datetime, timezone
from database.db import db


def _utc_now():
    return datetime.now(timezone.utc)


class Security(db.Model):
    __tablename__ = "securities"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    company_id = db.Column(
        db.Integer,
        db.ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    symbol = db.Column(db.String(50), nullable=False, index=True)
    exchange = db.Column(db.String(20), nullable=False, default="NSE", index=True)
    series = db.Column(db.String(20), nullable=False, default="EQ", index=True)
    isin = db.Column(db.String(20), nullable=True, index=True)
    currency = db.Column(db.String(10), nullable=False, default="INR")
    asset_type = db.Column(db.String(50), nullable=False, default="Equity")
    listing_date = db.Column(db.Date, nullable=True)
    paid_up_value = db.Column(db.Numeric(12, 2), nullable=True)
    market_lot = db.Column(db.Integer, nullable=True)
    face_value = db.Column(db.Numeric(12, 2), nullable=True)
    is_active = db.Column(db.Boolean, nullable=False, default=True, index=True)
    source = db.Column(db.String(100), nullable=False, default="NSE")
    source_updated_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=_utc_now)
    updated_at = db.Column(db.DateTime, nullable=False, default=_utc_now, onupdate=_utc_now)

    __table_args__ = (
        db.UniqueConstraint(
            "exchange",
            "symbol",
            "series",
            name="uq_security_exchange_symbol_series",
        ),
        db.Index("ix_securities_exchange_symbol", "exchange", "symbol"),
    )

    def to_dict(self):
        return {
            "id": self.id,
            "company_id": self.company_id,
            "symbol": self.symbol,
            "exchange": self.exchange,
            "series": self.series,
            "isin": self.isin,
            "currency": self.currency,
            "asset_type": self.asset_type,
            "listing_date": self.listing_date.isoformat() if self.listing_date else None,
            "paid_up_value": float(self.paid_up_value) if self.paid_up_value is not None else None,
            "market_lot": self.market_lot,
            "face_value": float(self.face_value) if self.face_value is not None else None,
            "is_active": self.is_active,
            "source": self.source,
            "source_updated_at": self.source_updated_at.isoformat() if self.source_updated_at else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
