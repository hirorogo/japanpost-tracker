"""
ヤマト運輸 追跡スクレイパー

Usage:
    from japanpost_tracker import track_yamato

    result = track_yamato("123456789012")
    print(result.latest_status)   # "配達完了"
    print(result.entries)          # [TrackingEntry(...), ...]
"""

from __future__ import annotations

import re
from datetime import datetime, timezone, timedelta

import requests
from bs4 import BeautifulSoup

from japanpost_tracker.scraper import (
    TrackingResult,
    TrackingEntry,
    TrackingError,
    JST,
)

__all__ = ["track_yamato", "track_yamato_multi"]

YAMATO_URL = "https://toi.kuronekoyamato.co.jp/cgi-bin/tneko"


def track_yamato(tracking_number: str, *, timeout: int = 30) -> TrackingResult:
    """
    ヤマト運輸の追跡番号から配送状況を取得する

    Args:
        tracking_number: ヤマト運輸の送り状番号（ハイフンあり/なし両対応）
        timeout: リクエストタイムアウト（秒）

    Returns:
        TrackingResult: 追跡結果

    Raises:
        TrackingError: 取得失敗時
    """
    tracking_number = tracking_number.strip().replace("-", "")

    if not tracking_number.isdigit():
        raise TrackingError(f"無効な追跡番号: {tracking_number}")

    data = {
        "number01": tracking_number,
        "category": "0",
    }
    headers = {
        "User-Agent": "Mozilla/5.0 (compatible; YamatoTracker/1.0)",
    }

    try:
        resp = requests.post(YAMATO_URL, data=data, headers=headers, timeout=timeout)
        resp.raise_for_status()
    except requests.RequestException as e:
        raise TrackingError(f"リクエスト失敗: {e}") from e

    soup = BeautifulSoup(resp.text, "html.parser")

    # ── 追跡結果ブロックを探す ──
    invoice_block = soup.find("div", class_="parts-tracking-invoice-block")
    if not invoice_block:
        raise TrackingError(f"追跡結果が見つかりません: {tracking_number}")

    # ── ステータス取得 ──
    state_title = invoice_block.find("h4", class_="tracking-invoice-block-state-title")
    status_text = state_title.get_text(strip=True) if state_title else ""

    # エラーチェック
    state_div = invoice_block.find("div", class_=re.compile(r"tracking-invoice-block-state"))
    is_error = state_div and "is-urgent-red" in state_div.get("class", []) if state_div else False

    if is_error or status_text in ("伝票番号誤り", "伝票番号未登録"):
        summary = invoice_block.find("div", class_="tracking-invoice-block-state-summary")
        error_detail = summary.get_text(strip=True) if summary else status_text
        raise TrackingError(f"追跡番号エラー ({tracking_number}): {error_detail}")

    # ── 履歴情報をJavaScript (PRINT関数) から抽出 ──
    entries: list[TrackingEntry] = []

    # サーバーサイドで埋め込まれたPRINT_0関数からテーブルデータを抽出
    scripts = soup.find_all("script")
    for script in scripts:
        script_text = script.string or ""
        if "PRINT_0" not in script_text:
            continue

        # PRINT_0関数内の swd.writeln 行を抽出
        print_match = re.search(r"function PRINT_0\(\)\{(.+?)PRINT_HOOTER", script_text, re.DOTALL)
        if not print_match:
            continue

        print_body = print_match.group(1)

        # swd.writeln の中のHTMLを結合
        writeln_parts = re.findall(r"swd\.writeln\('(.+?)'\);", print_body)
        detail_html = "".join(writeln_parts)

        # HTMLをパース
        detail_soup = BeautifulSoup(detail_html, "html.parser")
        tables = detail_soup.find_all("table")

        for table in tables:
            rows = table.find_all("tr")
            for row in rows:
                tds = row.find_all("td")
                if len(tds) >= 4:
                    # 最初のtdが「荷物状態」的なテキスト（ヘッダー行はスキップ）
                    cell_texts = [td.get_text(strip=True) for td in tds]

                    # ヘッダー行や空行をスキップ
                    if not cell_texts[0] or cell_texts[0] in ("荷物状態", "商品名"):
                        continue

                    # ヤマトの詳細テーブル: 荷物状態 | 日付 | 時刻 | 担当店名 | 担当店コード
                    status = cell_texts[0]
                    date_str = cell_texts[1] if len(cell_texts) > 1 else ""
                    time_str = cell_texts[2] if len(cell_texts) > 2 else ""
                    office = cell_texts[3] if len(cell_texts) > 3 else ""
                    office_code = cell_texts[4] if len(cell_texts) > 4 else ""

                    date_combined = f"{date_str} {time_str}".strip()

                    entries.append(TrackingEntry(
                        date=date_combined,
                        status=status,
                        detail=office_code,
                        office=office,
                    ))
        break

    # ── レスポンシブHTML側からも履歴を試行 ──
    if not entries:
        detail_block = invoice_block.find("div", class_="tracking-invoice-block-detail")
        if detail_block:
            rows = detail_block.find_all("tr")
            for row in rows:
                tds = row.find_all("td")
                if len(tds) >= 3:
                    cell_texts = [td.get_text(strip=True) for td in tds]
                    if not cell_texts[0]:
                        continue
                    entries.append(TrackingEntry(
                        date=cell_texts[1] if len(cell_texts) > 1 else "",
                        status=cell_texts[0],
                        detail=cell_texts[4] if len(cell_texts) > 4 else "",
                        office=cell_texts[3] if len(cell_texts) > 3 else "",
                    ))

    # エントリがなくてもステータスがある場合は単一エントリとして追加
    if not entries and status_text:
        summary = invoice_block.find("div", class_="tracking-invoice-block-state-summary")
        summary_text = summary.get_text(strip=True) if summary else ""
        entries.append(TrackingEntry(
            date=datetime.now(JST).strftime("%m/%d %H:%M"),
            status=status_text,
            detail=summary_text,
        ))

    return TrackingResult(
        tracking_number=tracking_number,
        product_type="ヤマト運輸",
        entries=entries,
        contacts=[],
        checked_at=datetime.now(JST).isoformat(),
        carrier="yamato",
    )


def track_yamato_multi(tracking_numbers: list[str], *, timeout: int = 30) -> list[TrackingResult | TrackingError]:
    """
    複数のヤマト運輸追跡番号を一括取得する

    Args:
        tracking_numbers: 追跡番号のリスト
        timeout: リクエストタイムアウト（秒）

    Returns:
        list: TrackingResult または TrackingError のリスト
    """
    results = []
    for number in tracking_numbers:
        try:
            results.append(track_yamato(number, timeout=timeout))
        except TrackingError as e:
            results.append(e)
    return results
