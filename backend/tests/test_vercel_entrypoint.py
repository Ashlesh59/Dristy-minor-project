import unittest
import sys
import os
from unittest.mock import patch, MagicMock

class TestVercelEntrypoint(unittest.TestCase):
    @patch.dict(os.environ, {
        "INVESTIQ_TEST_RUN": "",
        "DATABASE_URL": "sqlite:///:memory:",
        "SECRET_KEY": "test-vercel-secret-key",
        "GEMINI_API_KEY": "test-gemini-key",
        "CORS_ALLOWED_ORIGINS": "https://test.vercel.app",
        "FLASK_DEBUG": "False"
    })
    def test_vercel_flask_application(self):
        # We need to test the api/index.py module without side effects
        
        # Save the original path
        original_path = sys.path.copy()
        
        try:
            # Add project root to sys.path
            project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
            if project_root not in sys.path:
                sys.path.insert(0, project_root)
                
            import importlib
            if "config" in sys.modules:
                importlib.reload(sys.modules["config"])
            if "app" in sys.modules:
                importlib.reload(sys.modules["app"])
                
            # Import api.index
            import api.index as index
            
            # Assert that a Flask application exists
            self.assertIsNotNone(index.app)
            self.assertEqual(index.app.name, "app")
            
            # Assert that /api/health is registered
            routes = [str(p) for p in index.app.url_map.iter_rules()]
            self.assertIn("/api/health", routes)
            
            # Assert that blueprints are registered
            blueprints = index.app.blueprints.keys()
            self.assertIn("auth", blueprints)
            self.assertIn("companies", blueprints)
            self.assertIn("securities", blueprints)
            
        finally:
            sys.path = original_path

if __name__ == "__main__":
    unittest.main()
