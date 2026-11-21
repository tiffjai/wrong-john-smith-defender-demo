from pathlib import Path

PKG = Path(__file__).resolve().parent
ROOT = PKG.parent
FIXTURES = PKG / "fixtures"
FEEDS = FIXTURES / "feeds"
KYC_V1 = FIXTURES / "kyc" / "customers_v1.json"
ACTORS = FIXTURES / "actors.json"
POLICIES = FIXTURES / "jurisdiction_policies.json"
REPLAYS = FIXTURES / "challenger_replays"
DRAFT_POLICY = PKG / "config" / "draft_policy.json"
FROZEN_POLICY = PKG / "config" / "frozen_policy.json"
SCHEMA_DIR = PKG / "schema"
DEFAULT_DB = ROOT / "rescreen_state" / "rescreen.sqlite"
EXPORT_DIR = ROOT / "exports" / "rescreen"
FEED_FILES = {("UK", "V1"): FEEDS / "uk_v1.json", ("UK", "V2"): FEEDS / "uk_v2.json",
              ("UK", "V3_MALFORMED"): FEEDS / "uk_v3_malformed.json",
              ("US", "V1"): FEEDS / "us_v1.json", ("CN", "V1"): FEEDS / "cn_v1.json"}
