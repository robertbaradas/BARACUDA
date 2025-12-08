"""
Global configuration for the stock data viewer application.

Update `API_KEY` with your Polygon.io API key.
"""

from __future__ import annotations
import os

# --- Polygon API ---
API_KEY: str = "E30hbMa_tamUFVJ7j9iGvP5F0kOHPdi_"  # Replace or set via environment in Phase 2

# --- Timings (milliseconds for Qt, seconds for others) ---
SNAPSHOT_REFRESH_SECONDS: int = 10
WS_RECONNECT_DELAY_SECONDS: float = 1.0
LOAD_GUARD_SAFETY_MS: int = 5000
WS_STOP_WAIT_MS: int = 1800
WS_START_GRACE_MS: int = 280

# --- Chart ---
CHART_LOOKBACK_DAYS: int = 365  # ~1 year
CHART_INTRADAY_REFRESH_MS: int = 45000  # 45s refresh for intraday timeframes/levels
CHART_DAILY_REFRESH_MS: int = 120000    # 120s refresh for daily timeframes/levels

# --- Logging ---
LOG_LEVEL: str = "INFO"

# --- Chart Interaction ---
CHART_TRANSITION_ENABLED: bool = True
CHART_TRANSITION_DURATION_MS: int = 1300
CHART_ZOOM_ANIMATION_DURATION_MS: int = 150

# ============================================================================
# PHASE 2: Trading, Portfolio, and ML Configuration
# ============================================================================

# Supabase Configuration
SUPABASE_URL = "https://byxtanngfywoplffgybt.supabase.co"  # e.g., https://xxxxx.supabase.co
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImJ5eHRhbm5nZnl3b3BsZmZneWJ0Iiwicm9sZSI6ImFub24iLCJpYXQiOjE3NjI4ODg1MTcsImV4cCI6MjA3ODQ2NDUxN30.XRPvcT_jwoNjVz4QsAEB469xK0RclDh3wV8kuFOFH5E"     # Your project's anon/public key
# Optional: service key for username-based login resolution (set via environment for safety)
SUPABASE_SERVICE_KEY = os.getenv("SUPABASE_SERVICE_KEY")  # your service role key, do NOT commit

# Portfolio Configuration
STARTING_CAPITAL = 10000.0  # Default starting cash for new accounts
MARK_PRICE_SOURCE = "LAST_TRADE"  # Options: "LAST_TRADE" or "MIDPOINT"

# Trading Configuration
ENABLE_SLIPPAGE = False  # Apply slippage simulation to fills
SLIPPAGE_BPS = 5  # Basis points of slippage (if enabled)
ENABLE_COMMISSION = False  # Charge commission on trades
COMMISSION_PER_SHARE = 0.0  # Commission per share (if enabled)
MIN_COMMISSION = 0.0  # Minimum commission per trade (if enabled)

# Time & Sales Configuration
TAPE_MAX_ROWS = 500  # Maximum rows in Time & Sales tape before trimming
TAPE_BACKFILL_ENABLED = True  # Backfill today's trades on ticker load
