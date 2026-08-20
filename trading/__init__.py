"""
AI Trading Engine Package

Provides a complete autonomous trading system with:
- Multi-symbol, multi-timeframe market scanning
- Feature engineering (30+ indicators)
- Market regime detection
- ML-based scoring (future)
- Ensemble opportunity scoring
- Risk engine with final authority
- Automatic position management
- Paper trading with full persistence
"""

from trading.engine import AIEngine

# Singleton engine instance
_engine = None


def get_engine():
    """Get or create the singleton AI engine."""
    global _engine
    if _engine is None:
        _engine = AIEngine()
        _engine.init_db()
    return _engine
