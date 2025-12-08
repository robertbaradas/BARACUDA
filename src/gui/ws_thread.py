from __future__ import annotations

import asyncio
from typing import Optional

from PyQt5 import QtCore

from src.polygon_client import PolygonClient


class WsThread(QtCore.QThread):
    trade_signal = QtCore.pyqtSignal(dict)
    status_signal = QtCore.pyqtSignal(str)

    def __init__(self, client: PolygonClient, ticker: str, parent: Optional[QtCore.QObject] = None):
        super().__init__(parent)
        self.client = client
        self.ticker = ticker
        self._stop_event: Optional[asyncio.Event] = None

    def run(self) -> None:  # noqa: D401
        """Run an asyncio loop for the WebSocket stream."""
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        self._stop_event = asyncio.Event()

        async def _runner():
            await self.client.stream_ticker(
                ticker=self.ticker,
                on_data=self.trade_signal.emit,
                on_status=self.status_signal.emit,
                stop_event=self._stop_event,
            )

        try:
            loop.run_until_complete(_runner())
        finally:
            try:
                pending = asyncio.all_tasks(loop)
                for task in pending:
                    task.cancel()
                loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
            except Exception:
                pass
            loop.stop()
            loop.close()

    def stop(self) -> None:
        if self._stop_event and not self._stop_event.is_set():
            self._stop_event.set()
