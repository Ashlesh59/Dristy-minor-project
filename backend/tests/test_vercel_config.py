import unittest
import json
import os

class TestVercelConfig(unittest.TestCase):
    def test_vercel_json_routing_structure(self):
        project_root = os.path.join(os.path.dirname(__file__), "..", "..")
        vercel_json_path = os.path.join(project_root, "vercel.json")
        
        self.assertTrue(os.path.exists(vercel_json_path))
        
        with open(vercel_json_path, "r") as f:
            config = json.load(f)
            
        self.assertIn("rewrites", config)
        rewrites = config["rewrites"]
        self.assertTrue(len(rewrites) > 0)
        
        api_rewrite = None
        for rewrite in rewrites:
            if rewrite.get("source", "").startswith("/api"):
                api_rewrite = rewrite
                break
                
        self.assertIsNotNone(api_rewrite, "Missing /api rewrite rule")
        self.assertEqual(api_rewrite["source"], "/api/:path*")
        self.assertEqual(api_rewrite["destination"], "/api/index")

if __name__ == "__main__":
    unittest.main()
