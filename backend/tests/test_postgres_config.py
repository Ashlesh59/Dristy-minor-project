import unittest
import os
from unittest.mock import patch, MagicMock

# Set testing environment before importing app
os.environ["INVESTIQ_TEST_RUN"] = "1"

from app import create_app
from database.migrations import run_migrations

class TestPostgresConfig(unittest.TestCase):
    def setUp(self):
        # Clear environment overrides
        if "DATABASE_URL" in os.environ:
            del os.environ["DATABASE_URL"]
        if "FLASK_DEBUG" in os.environ:
            del os.environ["FLASK_DEBUG"]
        if "SECRET_KEY" in os.environ:
            del os.environ["SECRET_KEY"]
        if "GEMINI_API_KEY" in os.environ:
            del os.environ["GEMINI_API_KEY"]
        if "CORS_ALLOWED_ORIGINS" in os.environ:
            del os.environ["CORS_ALLOWED_ORIGINS"]

    @patch.dict(os.environ, {"DATABASE_URL": "postgres://user:pass@host/db"})
    def test_database_url_normalization(self):
        # We need to re-import or reload config because it evaluates on import.
        # But we can just test the logic by manually doing what config.py does.
        # Actually config.py evaluates os.environ at import time, so we must reload it.
        import importlib
        import config
        importlib.reload(config)
        
        self.assertEqual(config.Config.SQLALCHEMY_DATABASE_URI, "postgresql://user:pass@host/db")
        self.assertEqual(config.Config.SQLALCHEMY_ENGINE_OPTIONS, {"pool_pre_ping": True})

    def test_local_sqlite_fallback(self):
        import importlib
        import config
        if "DATABASE_URL" in os.environ:
            del os.environ["DATABASE_URL"]
        importlib.reload(config)
        
        self.assertTrue(config.Config.SQLALCHEMY_DATABASE_URI.startswith("sqlite:///"))
        self.assertEqual(config.Config.SQLALCHEMY_ENGINE_OPTIONS, {})

    @patch("database.migrations.logging.getLogger")
    def test_postgres_skips_migrations(self, mock_logger):
        mock_db = MagicMock()
        mock_db.engine.dialect.name = "postgresql"
        
        run_migrations(mock_db)
        
        mock_logger.return_value.info.assert_called_once()
        # Ensure sqlite_master execute was not called
        mock_db.engine.begin.assert_not_called()

    @patch("database.migrations.logging.getLogger")
    def test_sqlite_runs_migrations(self, mock_logger):
        mock_db = MagicMock()
        mock_db.engine.dialect.name = "sqlite"
        mock_connection = MagicMock()
        mock_db.engine.begin.return_value.__enter__.return_value = mock_connection
        
        run_migrations(mock_db)
        
        mock_logger.return_value.info.assert_not_called()
        mock_connection.execute.assert_called()

    @patch.dict(os.environ, {"FLASK_DEBUG": "False"})
    def test_missing_production_secrets_fails(self):
        # We need to temporarily remove the sentinel to test production startup checks
        sentinel_value = os.environ.get("INVESTIQ_TEST_RUN")
        if sentinel_value:
            del os.environ["INVESTIQ_TEST_RUN"]
            
        import importlib
        import config
        import app
        importlib.reload(config)
        importlib.reload(app)
        
        with self.assertRaises(RuntimeError) as context:
            app.create_app()
            
        self.assertIn("SECRET_KEY must be set", str(context.exception))

        
        os.environ["SECRET_KEY"] = "strong-prod-key"
        importlib.reload(config)
        importlib.reload(app)
        
        with self.assertRaises(RuntimeError) as context:
            app.create_app()
        self.assertIn("DATABASE_URL is required", str(context.exception))
        
        os.environ["DATABASE_URL"] = "postgresql://user:pass@host/db"
        importlib.reload(config)
        importlib.reload(app)
        os.environ.pop("GEMINI_API_KEY", None)
        
        with self.assertRaises(RuntimeError) as context:
            app.create_app()
        self.assertIn("GEMINI_API_KEY is required", str(context.exception))
        
        os.environ["GEMINI_API_KEY"] = "fake-key"
        importlib.reload(config)
        importlib.reload(app)
        
        with self.assertRaises(RuntimeError) as context:
            app.create_app()
        self.assertIn("CORS_ALLOWED_ORIGINS must be set", str(context.exception))
        
        if sentinel_value:
            os.environ["INVESTIQ_TEST_RUN"] = sentinel_value

if __name__ == "__main__":
    unittest.main()
