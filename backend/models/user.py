"""
models/user.py
--------------------------------------------------------------------------
The User model -- represents one row in the "user" database table.
--------------------------------------------------------------------------
"""

from datetime import datetime

from werkzeug.security import generate_password_hash, check_password_hash

from database.db import db


class User(db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    email = db.Column(db.String(255), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    # Optional profile fields (Phase: Profile). All nullable so existing
    # rows created before this column existed remain valid with no
    # backfill required -- see database/migrations.py for the ALTER
    # TABLE statements that add these columns to an existing SQLite
    # file without touching any existing data.
    company = db.Column(db.String(200), nullable=True)
    job_role = db.Column(db.String(120), nullable=True)
    phone = db.Column(db.String(30), nullable=True)
    country = db.Column(db.String(100), nullable=True)
    timezone = db.Column(db.String(100), nullable=True)

    def set_password(self, plain_password):
        # Explicitly pinned to "pbkdf2:sha256" instead of relying on
        # Werkzeug's default (scrypt). scrypt requires hashlib to have
        # been built with OpenSSL's scrypt support, which this Python
        # 3.9 environment doesn't have (confirmed: hashlib.scrypt is
        # missing here), causing set_password() to fail. PBKDF2-SHA256
        # is implemented purely in Python's standard hashlib with no
        # such dependency, and is still a strong, salted, industry-
        # standard algorithm for password storage.
        self.password_hash = generate_password_hash(plain_password, method="pbkdf2:sha256")

    def check_password(self, plain_password):
        return check_password_hash(self.password_hash, plain_password)

    def to_public_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "email": self.email,
            "created_at": self.created_at.isoformat(),
            "company": self.company,
            "job_role": self.job_role,
            "phone": self.phone,
            "country": self.country,
            "timezone": self.timezone,
        }

    # ----------------------------------------------------------------
    # PHASE 5: relationship to Research
    # ----------------------------------------------------------------
    # This doesn't add or change any column on `users` -- it's a
    # Python-level convenience so code can do `user.research_records`
    # to get all of a user's research requests, without writing a
    # manual query. cascade="all, delete-orphan" means if a User row
    # were ever deleted, their research rows go with it automatically,
    # so there's no way to end up with orphaned research pointing at a
    # user that no longer exists. lazy="dynamic" returns a query
    # object (rather than loading every row immediately), which keeps
    # this cheap even for a user with a lot of research history.
    research_records = db.relationship(
        "Research",
        back_populates="user",
        cascade="all, delete-orphan",
        lazy="dynamic",
    )
