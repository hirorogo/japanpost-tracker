"""
japanpost-tracker - 日本郵便追跡スクレイパー

pip install git+https://github.com/hirorogo/japanpost-tracker.git

Usage:
    from japanpost_tracker import track, track_multi

    result = track("1234567890123")
    print(result.latest_status)
    print(result.entries)
    print(result.to_json())
"""

from japanpost_tracker.scraper import (
    track,
    track_multi,
    TrackingResult,
    TrackingEntry,
    ContactOffice,
    TrackingError,
)

__version__ = "1.0.0"
__all__ = [
    "track",
    "track_multi",
    "TrackingResult",
    "TrackingEntry",
    "ContactOffice",
    "TrackingError",
]
