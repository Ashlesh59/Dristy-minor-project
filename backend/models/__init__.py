# models/
# --------------------------------------------------------------------
# Every model is imported here so that a single `import models` (done
# once in app.py, before db.create_all() runs) pulls in every table
# definition. Research must be imported after User since it declares a
# db.relationship() back to User -- SQLAlchemy resolves relationships
# by class name at configure-time, so both classes need to have been
# defined before either relationship is actually used, but the import
# order itself doesn't need to be stricter than "both get imported."

from models.user import User  # noqa: F401
from models.research import Research  # noqa: F401
