"""
models/research.py
--------------------------------------------------------------------------
The Research model -- represents one row in the "research" table: a
single investment-research request a logged-in user has created.

Phase 5 only stores the request itself (what company, what ticker,
what kind of research, and its status). It does NOT fetch live
financial data, call any external API, or run any AI analysis -- those
are later phases. `status` exists now so this model is already shaped
for that future work: a later phase can flip a row from "pending" to
"processing" to "completed"/"failed" as it does the real work, without
needing to change this table again.
--------------------------------------------------------------------------
"""

import json
from datetime import datetime

from database.db import db


class Research(db.Model):
    __tablename__ = "research"

    id = db.Column(db.Integer, primary_key=True)

    # Foreign key to users.id -- ties every research record to exactly
    # one user. This is set by the route from session["user_id"] only
    # (see routes/research.py); it is never accepted from the request
    # body, so a client can't create a research record "as" another
    # user.
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)

    company_name = db.Column(db.String(200), nullable=False)
    ticker_symbol = db.Column(db.String(20), nullable=False)

    # What kind of research this is (e.g. "general", and more specific
    # types in later phases). Defaults to "general" so research_type
    # can be omitted entirely in the request body.
    research_type = db.Column(db.String(50), nullable=False, default="general")

    # One of: pending, processing, completed, failed. Every request
    # starts as "pending" -- nothing in Phase 5 ever moves it past
    # that, since no actual processing happens yet.
    status = db.Column(db.String(20), nullable=False, default="pending")

    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    # updated_at is set once at creation and then re-set automatically
    # by SQLAlchemy every time an existing row is modified and
    # committed, thanks to onupdate=... -- useful once a later phase
    # starts changing `status` as research actually runs.
    updated_at = db.Column(
        db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )

    # Persistence for real, previously-fetched/generated data (see
    # database/migrations.py for how these columns get added to an
    # existing SQLite file). Stored as JSON text rather than as
    # separate normalized tables since the shape of each comes from an
    # external API/AI response, not from a fixed internal schema --
    # this avoids needing a schema migration every time Alpha Vantage
    # or Gemini's response shape changes slightly. All nullable: a
    # freshly-created research record has none of this yet.
    financial_data = db.Column(db.Text, nullable=True)
    news_data = db.Column(db.Text, nullable=True)
    analysis_data = db.Column(db.Text, nullable=True)
    report_data = db.Column(db.Text, nullable=True)
    ai_score = db.Column(db.Integer, nullable=True)
    recommendation = db.Column(db.String(50), nullable=True)

    # The other side of the User -> Research relationship (see the
    # matching db.relationship added in models/user.py). Lets code do
    # `research_record.user` to get the owning User object if ever
    # needed, without writing a manual query.
    user = db.relationship("User", back_populates="research_records")

    @staticmethod
    def _load_json(text):
        """Best-effort JSON decode -- returns None for empty/invalid
        text instead of raising, since a persisted column being blank
        or (in some future bug) malformed shouldn't take down every
        endpoint that calls to_dict()."""
        if not text:
            return None
        try:
            return json.loads(text)
        except (ValueError, TypeError):
            return None

    def to_dict(self, include_details=True):
        """
        Only the fields that are safe and useful to return from the
        API. Deliberately excludes nothing sensitive here since
        Research has no secrets -- but keeping this method, same as
        User.to_public_dict(), means the route code never has to
        hand-build this dictionary itself or risk exposing an internal
        field by accident later.

        `include_details=False` (used by the list endpoint) leaves out
        the persisted financial/news/analysis/report JSON blobs, which
        can be large and aren't needed to render a list of saved
        research records -- ai_score/recommendation/status are enough
        for that.
        """
        data = {
            "id": self.id,
            "user_id": self.user_id,
            "company_name": self.company_name,
            "ticker_symbol": self.ticker_symbol,
            "research_type": self.research_type,
            "status": self.status,
            "ai_score": self.ai_score,
            "recommendation": self.recommendation,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }
        if include_details:
            data["financial_data"] = self._load_json(self.financial_data)
            data["news_data"] = self._load_json(self.news_data)
            data["analysis_data"] = self._load_json(self.analysis_data)
            data["report_data"] = self._load_json(self.report_data)
        return data
