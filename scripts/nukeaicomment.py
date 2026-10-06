#!/usr/bin/env python3
"""Point d'entrée de NukeAIComment."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from nukeai.cli import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
