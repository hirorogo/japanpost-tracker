"""
Japan Post 追跡スクレイパー

Usage:
    from japanpost_tracker import track

    result = track("1234567890123")
    print(result.latest_status)   # "引受"
    print(result.entries)          # [TrackingEntry(...), ...]

    # 複数番号を一括取得
    results = track_multi(["1234567890123", "123456789012"])
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone, timedelta
from typing import Optional

import requests
from bs4 import BeautifulSoup

__all__ = [
    "track",
    "track_multi",
    "TrackingResult",
    "TrackingEntry",
    "ContactOffice",
    "TrackingError",
]

JAPANPOST_URL = "https://trackings.post.japanpost.jp/services/srv/search/direct"
YAMATO_URL = "https://toi.kuronekoyamato.co.jp/cgi-bin/tneko"
JST = timezone(timedelta(hours=9))


class TrackingError(Exception):
    """追跡情報の取得に失敗した場合の例外"""
    pass


@dataclass
class TrackingEntry:
    """配送履歴の1エントリ"""
    date: str
    status: str
    detail: str = ""
    office: str = ""
    prefecture: str = ""
    postal_code: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class ContactOffice:
    """問い合わせ窓口局"""
    type: str
    office: str
    phone: str

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class TrackingResult:
    """追跡結果"""
    tracking_number: str
    product_type: str = ""
    entries: list[TrackingEntry] = field(default_factory=list)
    contacts: list[ContactOffice] = field(default_factory=list)
    checked_at: str = ""
    carrier: str = "japanpost"

    @property
    def latest_status(self) -> Optional[str]:
        """最新の配送ステータス"""
        return self.entries[-1].status if self.entries else None

    @property
    def latest_entry(self) -> Optional[TrackingEntry]:
        """最新の履歴エントリ"""
        return self.entries[-1] if self.entries else None

    @property
    def is_delivered(self) -> bool:
        """配達済みかどうか"""
        if not self.entries:
            return False
        return self.entries[-1].status in (
            "お届け先にお届け済み", "お届け済み", "配達完了",
        )

    @property
    def entries_hash(self) -> str:
        """履歴データのハッシュ（変化検出用）"""
        content = json.dumps(
            [e.to_dict() for e in self.entries],
            ensure_ascii=False,
            sort_keys=True,
        )
        return hashlib.sha256(content.encode()).hexdigest()

    @property
    def url(self) -> str:
        """追跡ページURL"""
        if self.carrier == "yamato":
            return f"{YAMATO_URL}?number01={self.tracking_number}"
        return f"{JAPANPOST_URL}?searchKind=S002&locale=ja&reqCodeNo1={self.tracking_number}"

    @property
    def carrier_name(self) -> str:
        """配送業者名"""
        return {"japanpost": "日本郵便", "yamato": "ヤマト運輸"}.get(self.carrier, self.carrier)

    def to_dict(self) -> dict:
        return {
            "tracking_number": self.tracking_number,
            "carrier": self.carrier,
            "carrier_name": self.carrier_name,
            "product_type": self.product_type,
            "entries": [e.to_dict() for e in self.entries],
            "contacts": [c.to_dict() for c in self.contacts],
            "latest_status": self.latest_status,
            "is_delivered": self.is_delivered,
            "entries_hash": self.entries_hash,
            "url": self.url,
            "checked_at": self.checked_at,
        }

    def to_json(self, **kwargs) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=2, **kwargs)


def track(tracking_number: str, *, timeout: int = 30) -> TrackingResult:
    """
    追跡番号から配送状況を取得する

    Args:
        tracking_number: 日本郵便の追跡番号（ハイフンあり/なし両対応）
        timeout: リクエストタイムアウト（秒）

    Returns:
        TrackingResult: 追跡結果

    Raises:
        TrackingError: 取得失敗時

    Example:
        >>> from japanpost_tracker import track
        >>> result = track("1234567890123")
        >>> print(result.latest_status)
        '引受'
        >>> print(result.is_delivered)
        False
    """
    tracking_number = tracking_number.strip().replace("-", "")

    if not tracking_number.isdigit():
        raise TrackingError(f"無効な追跡番号: {tracking_number}")

    params = {
        "searchKind": "S002",
        "locale": "ja",
        "reqCodeNo1": tracking_number,
    }
    headers = {
        "User-Agent": "Mozilla/5.0 (compatible; JapanPostTracker/1.0)",
    }

    try:
        resp = requests.get(JAPANPOST_URL, params=params, headers=headers, timeout=timeout)
        resp.raise_for_status()
    except requests.RequestException as e:
        raise TrackingError(f"リクエスト失敗: {e}") from e

    soup = BeautifulSoup(resp.text, "html.parser")

    # ── 商品種別 ──
    product_type = ""
    detail_table = soup.find("table", attrs={"summary": "配達状況詳細"})
    if detail_table:
        tds = detail_table.find_all("td")
        if len(tds) >= 2:
            product_type = tds[1].get_text(strip=True)

    # 番号が見つからない場合
    if not detail_table:
        body_text = soup.get_text()
        if "お問い合わせ番号が見つかりません" in body_text or "該当する情報はありません" in body_text:
            raise TrackingError(f"追跡番号が見つかりません: {tracking_number}")

    # ── 履歴情報 ──
    history_table = soup.find("table", attrs={"summary": "履歴情報"})
    entries: list[TrackingEntry] = []

    if history_table:
        rows = history_table.find_all("tr")
        i = 2  # ヘッダー2行スキップ
        while i < len(rows):
            tds = rows[i].find_all("td")
            if not tds:
                i += 1
                continue

            entry_data: dict = {}
            if len(tds) >= 4:
                entry_data["date"] = tds[0].get_text(strip=True)
                entry_data["status"] = tds[1].get_text(strip=True)
                entry_data["detail"] = tds[2].get_text(strip=True)
                entry_data["office"] = tds[3].get_text(strip=True)
                if len(tds) >= 5:
                    entry_data["prefecture"] = tds[4].get_text(strip=True)

            # 次の行 = 郵便番号
            if i + 1 < len(rows):
                next_tds = rows[i + 1].find_all("td")
                if next_tds:
                    entry_data["postal_code"] = next_tds[0].get_text(strip=True)
                i += 2
            else:
                i += 1

            if entry_data.get("date"):
                entries.append(TrackingEntry(**entry_data))

    # ── お問い合わせ窓口局 ──
    contact_table = soup.find("table", attrs={"summary": "お問い合わせ窓口局"})
    contacts: list[ContactOffice] = []
    if contact_table:
        for row in contact_table.find_all("tr")[1:]:
            tds = row.find_all("td")
            if len(tds) >= 3:
                contacts.append(ContactOffice(
                    type=tds[0].get_text(strip=True),
                    office=tds[1].get_text(strip=True),
                    phone=tds[2].get_text(strip=True),
                ))

    return TrackingResult(
        tracking_number=tracking_number,
        product_type=product_type,
        entries=entries,
        contacts=contacts,
        checked_at=datetime.now(JST).isoformat(),
    )


def track_multi(tracking_numbers: list[str], *, timeout: int = 30) -> list[TrackingResult | TrackingError]:
    """
    複数の追跡番号を一括取得する

    取得失敗した番号は TrackingError オブジェクトとして返す（例外は投げない）

    Args:
        tracking_numbers: 追跡番号のリスト
        timeout: リクエストタイムアウト（秒）

    Returns:
        list: TrackingResult または TrackingError のリスト

    Example:
        >>> results = track_multi(["1234567890123", "000000000000"])
        >>> for r in results:
        ...     if isinstance(r, TrackingError):
        ...         print(f"Error: {r}")
        ...     else:
        ...         print(f"{r.tracking_number}: {r.latest_status}")
    """
    results = []
    for number in tracking_numbers:
        try:
            results.append(track(number, timeout=timeout))
        except TrackingError as e:
            results.append(e)
    return results
