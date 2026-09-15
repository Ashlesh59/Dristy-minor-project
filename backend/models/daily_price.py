"""
models/daily_price.py
--------------------------------------------------------------------------
DailyPrice model representing verified End-of-Day (EOD) OHLCV, turnover,
and delivery market data for a listed Security on an exchange.
--------------------------------------------------------------------------
"""

from datetime import datetime
from database.db import db


class DailyPrice(db.Model):
    __tablename__ = "daily_prices"

    id = db.Column(db.Integer, primary_key=True)
    security_id = db.Column(
        db.Integer,
        db.ForeignKey("securities.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    trading_date = db.Column(db.Date, nullable=False, index=True)

    # OHLC Prices (Stored as exact base-10 Decimal NUMERIC(14, 4))
    open_price = db.Column(db.Numeric(14, 4), nullable=False)
    high_price = db.Column(db.Numeric(14, 4), nullable=False)
    low_price = db.Column(db.Numeric(14, 4), nullable=False)
    close_price = db.Column(db.Numeric(14, 4), nullable=False)

    # Optional / Additional price fields
    last_price = db.Column(db.Numeric(14, 4), nullable=True)
    previous_close = db.Column(db.Numeric(14, 4), nullable=True)
    vwap = db.Column(db.Numeric(14, 4), nullable=True)

    # Volume and monetary quantities
    volume = db.Column(db.BigInteger, nullable=True)
    turnover = db.Column(db.Numeric(20, 4), nullable=True)  # Total traded value in INR
    trade_count = db.Column(db.Integer, nullable=True)

    # Delivery metrics
    deliverable_quantity = db.Column(db.BigInteger, nullable=True)
    deliverable_percentage = db.Column(db.Numeric(6, 2), nullable=True)

    # Provenance & Ingestion Metadata
    source = db.Column(db.String(50), nullable=False, default="NSE_UDIFF", index=True)
    source_file_sha256 = db.Column(db.String(64), nullable=False)
    source_row_number = db.Column(db.Integer, nullable=True)
    is_adjusted = db.Column(db.Boolean, nullable=False, default=False)

    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    updated_at = db.Column(
        db.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    # Relationship back to Security
    security = db.relationship("Security", backref=db.backref("daily_prices", lazy="dynamic"))

    __table_args__ = (
        db.UniqueConstraint(
            "security_id", "trading_date", "source",
            name="uq_daily_prices_security_date_source"
        ),
        db.Index("ix_daily_prices_security_trading_date", "security_id", "trading_date"),
    )

    def to_dict(self):
        return {
            "id": self.id,
            "security_id": self.security_id,
            "trading_date": self.trading_date.isoformat() if self.trading_date else None,
            "open_price": str(self.open_price) if self.open_price is not None else None,
            "high_price": str(self.high_price) if self.high_price is not None else None,
            "low_price": str(self.low_price) if self.low_price is not None else None,
            "close_price": str(self.close_price) if self.close_price is not None else None,
            "last_price": str(self.last_price) if self.last_price is not None else None,
            "previous_close": str(self.previous_close) if self.previous_close is not None else None,
            "vwap": str(self.vwap) if self.vwap is not None else None,
            "volume": self.volume,
            "turnover": str(self.turnover) if self.turnover is not None else None,
            "trade_count": self.trade_count,
            "deliverable_quantity": self.deliverable_quantity,
            "deliverable_percentage": str(self.deliverable_percentage) if self.deliverable_percentage is not None else None,
            "source": self.source,
            "source_file_sha256": self.source_file_sha256,
            "source_row_number": self.source_row_number,
            "is_adjusted": self.is_adjusted,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
