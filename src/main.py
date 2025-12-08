from __future__ import annotations

import logging
import sys

from PyQt5 import QtWidgets

from config import API_KEY, LOG_LEVEL
from src.polygon_client import PolygonClient
from src.gui import MainWindow


def main() -> int:
    logging.basicConfig(level=getattr(logging, LOG_LEVEL.upper(), logging.INFO))
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("websockets").setLevel(logging.WARNING)

    if not API_KEY or API_KEY == "YOUR_POLYGON_API_KEY_HERE":
        print("Please set your Polygon API key in config.py before running.")
        return 1

    client = PolygonClient(API_KEY)
    app = QtWidgets.QApplication(sys.argv)
    win = MainWindow(client)
    win.resize(1100, 800)
    win.show()
    return app.exec_()


if __name__ == "__main__":
    raise SystemExit(main())
