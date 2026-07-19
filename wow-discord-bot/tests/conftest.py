import os
import sys
from pathlib import Path

# Make sure the project root is importable when pytest is invoked from anywhere.
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# config.Settings has a few required fields (Discord/Blizzard creds). The real
# values live in .env and never in the repo, so seed harmless placeholders here
# BEFORE anything imports `config` — that way the suite is hermetic and doesn't
# depend on a developer's local .env being present.
os.environ.setdefault("DISCORD_TOKEN", "test-token")
os.environ.setdefault("BLIZZARD_CLIENT_ID", "test-id")
os.environ.setdefault("BLIZZARD_CLIENT_SECRET", "test-secret")

FIXTURES = Path(__file__).parent / "fixtures"


def load_fixture(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")
