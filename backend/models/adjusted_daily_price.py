"""
AdjustedDailyPrice Model — Represents derived split- and bonus-adjusted historical market data.
"""
from datetime import datetime
from database.db import db


class AdjustedDailyPrice(db.Model):
    """
    Stores derived adjusted daily price data calculated from raw DailyPrice and CorporateAction events.
    Raw DailyPrice records remain 100% untouched.
    """
    __tablename__ = "adjusted_daily_prices"

    id = db.Column(db.Integer, primary_key=True)
    daily_price_id = db.Column(
        db.Integer,
        db.ForeignKey("daily_prices.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    security_id = db.Column(
        db.Integer,
        db.ForeignKey("securities.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    trading_date = db.Column(db.Date, nullable=False, index=True)
    adjusted_open = db.Column(db.Numeric(14, 4), nullable=False)
    adjusted_high = db.Column(db.Numeric(14, 4), nullable=False)
    adjusted_low = db.Column(db.Numeric(14, 4), nullable=False)
    adjusted_close = db.Column(db.Numeric(14, 4), nullable=False)
    adjusted_volume = db.Column(db.BigInteger, nullable=True)
    cumulative_price_factor = db.Column(db.Numeric(18, 10), nullable=False)
    cumulative_volume_factor = db.Column(db.Numeric(18, 10), nullable=False)
    adjustment_method = db.Column(db.String(50), nullable=False, default="split_bonus_ratio")
    adjustment_version = db.Column(db.String(50), nullable=False, default="split_bonus_v1", index=True)
    calculated_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    # Relationships
    daily_price = db.relationship("DailyPrice", backref=db.backref("adjusted_prices", lazy="dynamic", cascade="all, delete-orphan"))
    security = db.relationship("Security", backref=db.backref("adjusted_prices", lazy="dynamic", cascade="all, delete-orphan"))

    __table_args__ = (
        db.UniqueConstraint("daily_price_id", "adjustment_version", name="uq_adjusted_daily_prices_daily_version"),
        db.Index("ix_adjusted_daily_prices_security_date_version", "security_id", "trading_date", "adjustment_version"),
    )

    def __repr__(self):
        return (
            f"<AdjustedDailyPrice id={self.id} security_id={self.security_id} "
            f"date={self.trading_date} close={self.adjusted_close} version='{self.adjustment_version}'>"
        )
