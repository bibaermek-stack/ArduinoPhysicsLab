"""tests/unit пакеті — domain entity-лерге арналған юнит-тесттер.

Бұл __init__.py тек жоба түбірін (project root) sys.path-қа қосу үшін
қажет, сондықтан тесттер `domain.entities...` модульдерін pytest қай
жерден іске қосылғанына қарамастан импорттай алады.
"""

import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))
