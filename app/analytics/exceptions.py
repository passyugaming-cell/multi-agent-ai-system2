class AnalyticsError(Exception):
    """Base exception for analytics domain errors."""
    pass


class InsufficientDataError(AnalyticsError):
    """Raised when historical data is insufficient for calculations or forecasting."""
    pass
