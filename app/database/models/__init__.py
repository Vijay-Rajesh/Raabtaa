"""
Re-export shim: the actual SQLAlchemy model classes live in `app/models/`.
This package exists to satisfy the requested project layout
(database/models) and to give Alembic a single place to import
"all models" from before calling target_metadata.
"""
from app.models import *  # noqa: F401,F403
from app.database.base import Base

__all__ = ["Base"]
