"""
Japan Post 追跡チェッカー (GitHub Actions 用)
- data/trackings.json に登録された追跡番号をチェック
- 前回の状態と比較し、変化があれば Discord Webhook で通知
"""

import json
import os
import sys
from datetime import datetime

import requests

# パッケージを import（pip install -e . 済み or PYTHONPATH で参照）
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from japanpost_tracker import track, TrackingResult, TrackingError

DATA_FILE = os.path.join(os.path.dirname(__file__), "..", "data", "trackings.json")
DISCORD_WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_URL", "")


def send_discord_notification(result: TrackingResult, is_new: bool = False):
    """Discord Webhook で通知を送信"""
    if not DISCORD_WEBHOOK_URL:
        print("DISCORD_WEBHOOK_URL が設定されていません。通知をスキップします。")
        return

    title = (
        f"📦 追跡番号を登録しました: {result.tracking_number}"
        if is_new
        else f"🚚 配送状況が更新されました: {result.tracking_number}"
    )
    color = 0x3498DB if is_new else 0x2ECC71

    fields = []
    if result.product_type:
        fields.append({"name": "商品種別", "value": result.product_type, "inline": True})

    for entry in result.entries:
        status_text = entry.status
        if entry.detail:
            status_text += f" ({entry.detail})"

        office_text = entry.office
        if entry.prefecture:
            office_text += f" ({entry.prefecture})"
        if entry.postal_code:
            office_text += f" 〒{entry.postal_code}"

        fields.append({
            "name": entry.date,
            "value": f"**{status_text}**\n{office_text}" if office_text else f"**{status_text}**",
            "inline": False,
        })

    if result.is_delivered:
        title = f"✅ 配達完了: {result.tracking_number}"
        color = 0xE74C3C

    embed = {
        "title": title,
        "color": color,
        "fields": fields,
        "footer": {"text": f"確認時刻: {result.checked_at}"},
        "url": result.url,
    }

    resp = requests.post(DISCORD_WEBHOOK_URL, json={"embeds": [embed]}, timeout=15)
    if resp.status_code == 204:
        print(f"  Discord 通知送信完了: {result.tracking_number}")
    else:
        print(f"  Discord 通知送信失敗: {resp.status_code} {resp.text}")


def load_data() -> dict:
    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def save_data(data: dict):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def register_tracking(tracking_number: str):
    """新しい追跡番号を登録"""
    tracking_number = tracking_number.strip().replace("-", "")
    data = load_data()
    is_new = tracking_number not in data

    if not is_new:
        print(f"追跡番号 {tracking_number} は既に登録済み。再チェックします...")
    else:
        print(f"追跡番号 {tracking_number} を登録します...")

    print("  追跡情報を取得中...")
    result = track(tracking_number)

    data[tracking_number] = {
        "entries_hash": result.entries_hash,
        "product_type": result.product_type,
        "latest_status": result.latest_status or "不明",
        "registered_at": data.get(tracking_number, {}).get("registered_at", datetime.now().isoformat()),
        "last_checked": result.checked_at,
    }

    save_data(data)
    print(f"  登録完了: {tracking_number} (最新: {result.latest_status})")
    send_discord_notification(result, is_new=is_new)


def check_all():
    """全追跡番号をチェック"""
    data = load_data()
    if not data:
        print("登録された追跡番号がありません。")
        return

    has_changes = False

    for tracking_number, stored in data.items():
        print(f"チェック中: {tracking_number}")
        try:
            result = track(tracking_number)
            old_hash = stored.get("entries_hash", "")

            if result.entries_hash != old_hash:
                print(f"  変化を検出!")
                print(f"    前回: {stored.get('latest_status', '不明')}")
                print(f"    今回: {result.latest_status}")

                data[tracking_number] = {
                    "entries_hash": result.entries_hash,
                    "product_type": result.product_type,
                    "latest_status": result.latest_status or "不明",
                    "registered_at": stored.get("registered_at", ""),
                    "last_checked": result.checked_at,
                }
                has_changes = True
                send_discord_notification(result)
            else:
                print(f"  変化なし (最新: {result.latest_status})")
                data[tracking_number]["last_checked"] = result.checked_at

        except TrackingError as e:
            print(f"  エラー: {tracking_number} - {e}")

    save_data(data)
    print(f"\n{'変更あり。' if has_changes else '変更なし。'}")


def remove_tracking(tracking_number: str):
    """追跡番号を削除"""
    tracking_number = tracking_number.strip().replace("-", "")
    data = load_data()

    if tracking_number in data:
        del data[tracking_number]
        save_data(data)
        print(f"追跡番号 {tracking_number} を削除しました。")
    else:
        print(f"追跡番号 {tracking_number} は登録されていません。")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("使用方法:")
        print("  python check.py register <追跡番号>")
        print("  python check.py check")
        print("  python check.py remove <追跡番号>")
        sys.exit(1)

    command = sys.argv[1]
    if command == "register" and len(sys.argv) >= 3:
        register_tracking(sys.argv[2])
    elif command == "check":
        check_all()
    elif command == "remove" and len(sys.argv) >= 3:
        remove_tracking(sys.argv[2])
    else:
        print(f"不明なコマンド: {command}")
        sys.exit(1)
