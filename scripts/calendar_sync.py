"""
TimeTree <-> Google Calendar 双方向同期スクリプト

同期で作成されたイベントは名前の末尾に「douki」を付けて管理する。
片方が変更されたらもう片方に反映する。

必要な環境変数:
  TIMETREE_ACCESS_TOKEN  - TimeTree パーソナルアクセストークン
  TIMETREE_CALENDAR_ID   - 同期対象の TimeTree カレンダーID
  GOOGLE_CREDENTIALS_JSON - Google サービスアカウントの認証情報 JSON
  GOOGLE_CALENDAR_ID     - 同期対象の Google カレンダーID (デフォルト: primary)
"""

import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests

# ---------------------------------------------------------------------------
# Google Calendar API (google-api-python-client)
# ---------------------------------------------------------------------------
from google.oauth2.service_account import Credentials as ServiceAccountCredentials
from googleapiclient.discovery import build

SYNC_MARKER = "douki"
DATA_DIR = Path(__file__).resolve().parent.parent / "data"
MAPPING_FILE = DATA_DIR / "sync_mappings.json"

JST = timezone(timedelta(hours=9))


# ===== データ永続化 =====

def load_mappings() -> dict:
    if MAPPING_FILE.exists():
        with open(MAPPING_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"mappings": []}


def save_mappings(data: dict) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with open(MAPPING_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


# ===== TimeTree API =====

class TimeTreeClient:
    BASE = "https://timetreeapis.com"

    def __init__(self, access_token: str, calendar_id: str):
        self.token = access_token
        self.calendar_id = calendar_id
        self.headers = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
            "Accept": "application/vnd.timetree.v1+json",
        }

    def get_upcoming_events(self, days: int = 30) -> list[dict]:
        """今日から days 日先までのイベントを取得する。"""
        now = datetime.now(JST)
        params = {
            "timezone": "Asia/Tokyo",
            "days": days,
        }
        url = f"{self.BASE}/calendars/{self.calendar_id}/upcoming_events"
        resp = requests.get(url, headers=self.headers, params=params, timeout=30)
        resp.raise_for_status()
        return resp.json().get("data", [])

    def get_event(self, event_id: str) -> dict | None:
        url = f"{self.BASE}/calendars/{self.calendar_id}/events/{event_id}"
        resp = requests.get(url, headers=self.headers, timeout=30)
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        return resp.json().get("data")

    def create_event(self, title: str, start: str, end: str,
                     all_day: bool = False, description: str = "") -> dict:
        payload = {
            "data": {
                "attributes": {
                    "category": "schedule",
                    "title": title,
                    "all_day": all_day,
                    "start_at": start,
                    "end_at": end,
                    "description": description,
                },
                "relationships": {
                    "label": {
                        "data": {
                            "id": f"{self.calendar_id},1",
                            "type": "label",
                        }
                    }
                },
            }
        }
        url = f"{self.BASE}/calendars/{self.calendar_id}/events"
        resp = requests.post(url, headers=self.headers,
                             json=payload, timeout=30)
        resp.raise_for_status()
        return resp.json().get("data")

    def update_event(self, event_id: str, title: str, start: str, end: str,
                     all_day: bool = False, description: str = "") -> dict:
        payload = {
            "data": {
                "attributes": {
                    "title": title,
                    "all_day": all_day,
                    "start_at": start,
                    "end_at": end,
                    "description": description,
                },
            }
        }
        url = f"{self.BASE}/calendars/{self.calendar_id}/events/{event_id}"
        resp = requests.put(url, headers=self.headers,
                            json=payload, timeout=30)
        resp.raise_for_status()
        return resp.json().get("data")

    def delete_event(self, event_id: str) -> None:
        url = f"{self.BASE}/calendars/{self.calendar_id}/events/{event_id}"
        resp = requests.delete(url, headers=self.headers, timeout=30)
        if resp.status_code not in (200, 204, 404):
            resp.raise_for_status()


# ===== Google Calendar API =====

class GoogleCalendarClient:
    SCOPES = ["https://www.googleapis.com/auth/calendar"]

    def __init__(self, credentials_json: str, calendar_id: str = "primary"):
        creds_info = json.loads(credentials_json)
        creds = ServiceAccountCredentials.from_service_account_info(
            creds_info, scopes=self.SCOPES
        )
        self.service = build("calendar", "v3", credentials=creds)
        self.calendar_id = calendar_id

    def get_upcoming_events(self, days: int = 30) -> list[dict]:
        now = datetime.now(JST)
        time_min = now.isoformat()
        time_max = (now + timedelta(days=days)).isoformat()
        events = []
        page_token = None
        while True:
            result = (
                self.service.events()
                .list(
                    calendarId=self.calendar_id,
                    timeMin=time_min,
                    timeMax=time_max,
                    singleEvents=True,
                    orderBy="startTime",
                    pageToken=page_token,
                )
                .execute()
            )
            events.extend(result.get("items", []))
            page_token = result.get("nextPageToken")
            if not page_token:
                break
        return events

    def get_event(self, event_id: str) -> dict | None:
        try:
            return (
                self.service.events()
                .get(calendarId=self.calendar_id, eventId=event_id)
                .execute()
            )
        except Exception:
            return None

    def create_event(self, title: str, start: str, end: str,
                     all_day: bool = False, description: str = "") -> dict:
        body: dict = {
            "summary": title,
            "description": description,
        }
        if all_day:
            body["start"] = {"date": start[:10]}
            body["end"] = {"date": end[:10]}
        else:
            body["start"] = {"dateTime": start, "timeZone": "Asia/Tokyo"}
            body["end"] = {"dateTime": end, "timeZone": "Asia/Tokyo"}
        return (
            self.service.events()
            .insert(calendarId=self.calendar_id, body=body)
            .execute()
        )

    def update_event(self, event_id: str, title: str, start: str, end: str,
                     all_day: bool = False, description: str = "") -> dict:
        body: dict = {
            "summary": title,
            "description": description,
        }
        if all_day:
            body["start"] = {"date": start[:10]}
            body["end"] = {"date": end[:10]}
        else:
            body["start"] = {"dateTime": start, "timeZone": "Asia/Tokyo"}
            body["end"] = {"dateTime": end, "timeZone": "Asia/Tokyo"}
        return (
            self.service.events()
            .update(
                calendarId=self.calendar_id, eventId=event_id, body=body
            )
            .execute()
        )

    def delete_event(self, event_id: str) -> None:
        try:
            self.service.events().delete(
                calendarId=self.calendar_id, eventId=event_id
            ).execute()
        except Exception:
            pass


# ===== ヘルパー =====

def _strip_marker(title: str) -> str:
    """タイトル末尾の SYNC_MARKER を除去して元のタイトルを返す。"""
    if title.endswith(f" {SYNC_MARKER}"):
        return title[: -(len(SYNC_MARKER) + 1)]
    return title


def _add_marker(title: str) -> str:
    """タイトル末尾に SYNC_MARKER を付与する。"""
    if title.endswith(f" {SYNC_MARKER}"):
        return title
    return f"{title} {SYNC_MARKER}"


def _is_synced(title: str) -> bool:
    return title.endswith(f" {SYNC_MARKER}")


def _tt_event_info(ev: dict) -> dict:
    """TimeTree イベントから正規化情報を取得。"""
    attrs = ev.get("attributes", {})
    return {
        "id": ev["id"],
        "title": attrs.get("title", ""),
        "start": attrs.get("start_at", ""),
        "end": attrs.get("end_at", ""),
        "all_day": attrs.get("all_day", False),
        "description": attrs.get("description", ""),
        "updated_at": attrs.get("updated_at", ""),
    }


def _gc_event_info(ev: dict) -> dict:
    """Google Calendar イベントから正規化情報を取得。"""
    start_raw = ev.get("start", {})
    end_raw = ev.get("end", {})
    all_day = "date" in start_raw and "dateTime" not in start_raw
    return {
        "id": ev["id"],
        "title": ev.get("summary", ""),
        "start": start_raw.get("dateTime", start_raw.get("date", "")),
        "end": end_raw.get("dateTime", end_raw.get("date", "")),
        "all_day": all_day,
        "description": ev.get("description", ""),
        "updated_at": ev.get("updated", ""),
    }


def _find_mapping(mappings: list, *, tt_id: str | None = None,
                  gc_id: str | None = None) -> dict | None:
    for m in mappings:
        if tt_id and m.get("timetree_id") == tt_id:
            return m
        if gc_id and m.get("google_id") == gc_id:
            return m
    return None


def _content_changed(info: dict, mapping: dict, prefix: str) -> bool:
    """マッピングに保存された前回情報と比較して変更があるか判定。"""
    for key in ("title", "start", "end", "all_day"):
        if str(info.get(key, "")) != str(mapping.get(f"{prefix}_{key}", "")):
            return True
    return False


def _save_to_mapping(mapping: dict, info: dict, prefix: str) -> None:
    for key in ("title", "start", "end", "all_day"):
        mapping[f"{prefix}_{key}"] = str(info.get(key, ""))


# ===== 同期ロジック =====

def sync(tt: TimeTreeClient, gc: GoogleCalendarClient) -> None:
    data = load_mappings()
    mappings: list = data["mappings"]

    tt_events = tt.get_upcoming_events(days=60)
    gc_events = gc.get_upcoming_events(days=60)

    tt_info_map = {ev["id"]: _tt_event_info(ev) for ev in tt_events}
    gc_info_map = {ev["id"]: _gc_event_info(ev) for ev in gc_events}

    processed_tt = set()
    processed_gc = set()

    # ------------------------------------------------------------------
    # 1. 既存マッピングの処理 (更新 / 削除検知)
    # ------------------------------------------------------------------
    to_remove = []
    for mapping in mappings:
        tt_id = mapping["timetree_id"]
        gc_id = mapping["google_id"]
        tt_info = tt_info_map.get(tt_id)
        gc_info = gc_info_map.get(gc_id)

        # 両方削除 → マッピング削除
        if tt_info is None and gc_info is None:
            to_remove.append(mapping)
            continue

        # TimeTree 側削除 → Google 側も削除
        if tt_info is None and gc_info is not None:
            print(f"[削除] Google: {gc_info['title']}")
            gc.delete_event(gc_id)
            to_remove.append(mapping)
            processed_gc.add(gc_id)
            continue

        # Google 側削除 → TimeTree 側も削除
        if gc_info is None and tt_info is not None:
            print(f"[削除] TimeTree: {tt_info['title']}")
            tt.delete_event(tt_id)
            to_remove.append(mapping)
            processed_tt.add(tt_id)
            continue

        # 両方存在 → 変更検知して反映
        tt_changed = _content_changed(tt_info, mapping, "tt")
        gc_changed = _content_changed(gc_info, mapping, "gc")

        if tt_changed and not gc_changed:
            # TimeTree が変更された → Google に反映
            new_title = _add_marker(_strip_marker(tt_info["title"]))
            print(f"[更新 TT→GC] {tt_info['title']}")
            gc.update_event(
                gc_id, new_title,
                tt_info["start"], tt_info["end"],
                tt_info["all_day"], tt_info["description"],
            )
            _save_to_mapping(mapping, tt_info, "tt")
            gc_new = _gc_event_info(gc.get_event(gc_id) or {})
            _save_to_mapping(mapping, gc_new, "gc")

        elif gc_changed and not tt_changed:
            # Google が変更された → TimeTree に反映
            new_title = _add_marker(_strip_marker(gc_info["title"]))
            print(f"[更新 GC→TT] {gc_info['title']}")
            tt.update_event(
                tt_id, new_title,
                gc_info["start"], gc_info["end"],
                gc_info["all_day"], gc_info["description"],
            )
            _save_to_mapping(mapping, gc_info, "gc")
            tt_new = _tt_event_info(tt.get_event(tt_id) or {})
            _save_to_mapping(mapping, tt_new, "tt")

        elif tt_changed and gc_changed:
            # 両方変更 → updated_at が新しい方を優先
            tt_up = tt_info.get("updated_at", "")
            gc_up = gc_info.get("updated_at", "")
            if tt_up >= gc_up:
                new_title = _add_marker(_strip_marker(tt_info["title"]))
                print(f"[競合→TT優先] {tt_info['title']}")
                gc.update_event(
                    gc_id, new_title,
                    tt_info["start"], tt_info["end"],
                    tt_info["all_day"], tt_info["description"],
                )
            else:
                new_title = _add_marker(_strip_marker(gc_info["title"]))
                print(f"[競合→GC優先] {gc_info['title']}")
                tt.update_event(
                    tt_id, new_title,
                    gc_info["start"], gc_info["end"],
                    gc_info["all_day"], gc_info["description"],
                )
            _save_to_mapping(mapping, tt_info, "tt")
            _save_to_mapping(mapping, gc_info, "gc")
        else:
            # 変更なし
            pass

        processed_tt.add(tt_id)
        processed_gc.add(gc_id)

    for m in to_remove:
        mappings.remove(m)

    # ------------------------------------------------------------------
    # 2. 新規イベントの同期 (douki マーカーなし = 元イベント)
    # ------------------------------------------------------------------

    # TimeTree の未処理イベント → Google に同期
    for tt_id, info in tt_info_map.items():
        if tt_id in processed_tt:
            continue
        if _is_synced(info["title"]):
            # 既に douki マーク付き = 他方から同期されたもの (マッピング消失時)
            continue
        title_with_marker = _add_marker(info["title"])
        print(f"[新規 TT→GC] {info['title']}")
        gc_ev = gc.create_event(
            title_with_marker, info["start"], info["end"],
            info["all_day"], info["description"],
        )
        gc_info = _gc_event_info(gc_ev)
        # TimeTree 側にも douki マーカーを付与
        tt.update_event(
            tt_id, title_with_marker,
            info["start"], info["end"],
            info["all_day"], info["description"],
        )
        info["title"] = title_with_marker
        new_mapping = {"timetree_id": tt_id, "google_id": gc_ev["id"]}
        _save_to_mapping(new_mapping, info, "tt")
        _save_to_mapping(new_mapping, gc_info, "gc")
        mappings.append(new_mapping)

    # Google の未処理イベント → TimeTree に同期
    for gc_id, info in gc_info_map.items():
        if gc_id in processed_gc:
            continue
        if _is_synced(info["title"]):
            continue
        title_with_marker = _add_marker(info["title"])
        print(f"[新規 GC→TT] {info['title']}")
        tt_ev = tt.create_event(
            title_with_marker, info["start"], info["end"],
            info["all_day"], info["description"],
        )
        tt_info = _tt_event_info(tt_ev)
        # Google 側にも douki マーカーを付与
        gc.update_event(
            gc_id, title_with_marker,
            info["start"], info["end"],
            info["all_day"], info["description"],
        )
        info["title"] = title_with_marker
        new_mapping = {"timetree_id": tt_ev["id"], "google_id": gc_id}
        _save_to_mapping(new_mapping, tt_info, "tt")
        _save_to_mapping(new_mapping, info, "gc")
        mappings.append(new_mapping)

    save_mappings(data)
    print(f"[完了] マッピング数: {len(mappings)}")


# ===== メイン =====

def main():
    token = os.environ.get("TIMETREE_ACCESS_TOKEN")
    tt_cal_id = os.environ.get("TIMETREE_CALENDAR_ID")
    gc_creds = os.environ.get("GOOGLE_CREDENTIALS_JSON")
    gc_cal_id = os.environ.get("GOOGLE_CALENDAR_ID", "primary")

    missing = []
    if not token:
        missing.append("TIMETREE_ACCESS_TOKEN")
    if not tt_cal_id:
        missing.append("TIMETREE_CALENDAR_ID")
    if not gc_creds:
        missing.append("GOOGLE_CREDENTIALS_JSON")

    if missing:
        print(f"エラー: 環境変数が未設定です: {', '.join(missing)}")
        sys.exit(1)

    tt = TimeTreeClient(token, tt_cal_id)
    gc = GoogleCalendarClient(gc_creds, gc_cal_id)

    print(f"同期開始: {datetime.now(JST).isoformat()}")
    sync(tt, gc)
    print(f"同期終了: {datetime.now(JST).isoformat()}")


if __name__ == "__main__":
    main()
