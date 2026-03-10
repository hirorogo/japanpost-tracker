"""
japanpost-tracker - 配送追跡スクレイパー (日本郵便 / ヤマト運輸)

pip install git+https://github.com/hirorogo/japanpost-tracker.git

Usage:
    from japanpost_tracker import track, track_multi, track_yamato

    # 日本郵便
    result = track("1234567890123")

    # ヤマト運輸
    result = track_yamato("123456789012")

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

from japanpost_tracker.yamato_scraper import (
    track_yamato,
    track_yamato_multi,
)

__version__ = "1.1.0"
__all__ = [
    "track",
    "track_multi",
    "track_yamato",
    "track_yamato_multi",
    "TrackingResult",
    "TrackingEntry",
    "ContactOffice",
    "TrackingError",
]
