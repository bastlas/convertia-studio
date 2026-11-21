"""Point d'entrée : ``python3 -m convertia_studio``."""

import sys

from .cli import main

if __name__ == "__main__":
    sys.exit(main())
