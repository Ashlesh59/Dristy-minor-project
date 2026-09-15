import os
from pathlib import Path

# Paths
BASE_DIR = Path(__file__).parent.resolve()
DATA_RAW_DIR = BASE_DIR / "data" / "raw"
DATA_PROCESSED_DIR = BASE_DIR / "data" / "processed"
MODELS_DIR = BASE_DIR / "models"
REPORTS_DIR = BASE_DIR / "reports"

# Model Details
MODEL_NAME = "InvestIQ AlphaModel v1"
MODEL_VERSION = "1.0.0"
PREDICTION_HORIZON_DAYS = 20

# Random Seed for reproducibility
RANDOM_SEED = 42

# Time Split Ratios
TRAIN_RATIO = 0.70
VAL_RATIO = 0.15
TEST_RATIO = 0.15

# Required Columns
REQUIRED_PRICES_COLUMNS = ["date", "security_id", "symbol", "close", "volume"]
REQUIRED_BENCHMARK_COLUMNS = ["date", "close"]
