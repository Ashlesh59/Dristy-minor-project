import unittest
import sys
import os
from unittest.mock import patch, MagicMock

class TestVercelEntrypoint(unittest.TestCase):
    @patch.dict(os.environ, {"INVESTIQ_TEST_RUN": "1", "FLASK_DEBUG": "True"})
    def test_vercel_flask_application(self):
        # We need to test the api/index.py module without side effects
        
        # Save the original path
        original_path = sys.path.copy()
        
        try:
            # Import api/index
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
            self.assertIn("company", blueprints)
            self.assertIn("securities", blueprints)
            
        finally:
            sys.path = original_path

if __name__ == "__main__":
    unittest.main()
