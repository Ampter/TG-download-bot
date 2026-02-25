import sys
from pathlib import Path

SCRIPTS_DIR = Path(__file__).parent.parent / "src"
sys.path.append(str(SCRIPTS_DIR))

# Temporary CI smoke-test file for PR workflow validation.
CI_SMOKE = True
