## Stock Data Viewer (Polygon.io Delayed)

A PyQt5 desktop application showing delayed stock trades, bid/ask via snapshot polling, and a daily candlestick chart using Polygon.io APIs. Built for the Stocks Developer (Individual) plan with delayed entitlements.

### Features
- Live price updates via WebSocket (T.*) with DELAYED status indicator
- Bid/Ask/Sizes via REST snapshot polling every 10s
- Daily stats and fundamentals
- 1-year daily candlestick chart via pyqtgraph
- Robust ticker switching and graceful thread lifecycle

### Requirements
See `requirements.txt`. You must provide your own Polygon API key.

### Setup
1. Create and activate a virtual environment
2. `pip install -r requirements.txt`
3. Edit `config.py` and set `API_KEY`
4. Run: `python -m src.main`

### Notes
- Data is delayed ~15 minutes by Polygon's delayed plan
- Quotes channel (Q.*) not entitled on delayed plan; bid/ask updated via snapshot
- Market status is heuristically determined by ET time

