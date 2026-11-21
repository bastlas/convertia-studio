#!/usr/bin/env python3
"""Ancien nom de l'outil, conservé pour compatibilité.

Préférez désormais :

    python3 -m convertia_studio --help          # ligne de commande
    python3 -m convertia_studio.gui             # interface graphique

"""

import sys

from convertia_studio.cli import main

if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
