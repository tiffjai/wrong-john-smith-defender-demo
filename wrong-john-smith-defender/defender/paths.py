from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RECORDS_PATH = ROOT / "data" / "records.json"
ALIAS_PATH = ROOT / "data" / "alias_table.json"
DRAFT_CONFIG_PATH = ROOT / "config" / "draft_config.json"
FROZEN_CONFIG_PATH = ROOT / "config" / "frozen_config.json"
REVIEWS_PATH = ROOT / "reviews" / "analyst_reviews.json"
EXPORTS_DIR = ROOT / "exports"
