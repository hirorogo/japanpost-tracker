# japanpost-tracker

日本郵便の追跡番号をスクレイプして配送状況を取得する Python ライブラリ & Discord 通知ボット。

GitHub Actions だけで動くサーバーレス構成。追跡番号を登録すると1時間おきに配送状況をチェックし、変化があれば Discord に通知します。

```
GitHub Actions (cron: 毎時0分)
  ↓
scripts/check.py (Python スクレイピング)
  ↓
Japan Post 追跡ページをスクレイプ
  ↓
data/trackings.json と比較
  ↓ 変化あり
Discord Webhook で通知
  ↓
data/trackings.json を更新 & git commit
```

---

## ライブラリとして使う（pip install）

誰でも `pip install` するだけで日本郵便の追跡情報を取得できます。

### インストール

```bash
pip install git+https://github.com/hirorogo/japanpost-tracker.git
```

### 基本的な使い方

```python
from japanpost_tracker import track

result = track("1234567890123")

print(result.latest_status)    # "引受"
print(result.product_type)     # "クリックポスト"
print(result.is_delivered)     # False
print(result.url)              # Japan Post 追跡ページURL

# 全履歴を取得
for entry in result.entries:
    print(f"{entry.date} | {entry.status} | {entry.office} ({entry.prefecture})")

# JSON として出力
print(result.to_json())

# dict に変換
data = result.to_dict()
```

### 複数番号を一括取得

```python
from japanpost_tracker import track_multi, TrackingError

results = track_multi(["1234567890123", "123456789012"])

for r in results:
    if isinstance(r, TrackingError):
        print(f"Error: {r}")
    else:
        print(f"{r.tracking_number}: {r.latest_status}")
```

### エラーハンドリング

```python
from japanpost_tracker import track, TrackingError

try:
    result = track("000000000000")
except TrackingError as e:
    print(f"取得失敗: {e}")
```

### 返却データ

| プロパティ | 型 | 説明 |
|---|---|---|
| `tracking_number` | `str` | 追跡番号 |
| `product_type` | `str` | 商品種別（ゆうパック、クリックポスト等） |
| `entries` | `list[TrackingEntry]` | 配送履歴リスト |
| `contacts` | `list[ContactOffice]` | 問い合わせ窓口局 |
| `latest_status` | `str \| None` | 最新ステータス |
| `latest_entry` | `TrackingEntry \| None` | 最新の履歴エントリ |
| `is_delivered` | `bool` | 配達完了フラグ |
| `entries_hash` | `str` | 履歴の SHA256 ハッシュ（変化検出用） |
| `url` | `str` | Japan Post 追跡ページURL |
| `checked_at` | `str` | 取得日時 (ISO 8601) |

---

## フォークして Discord 通知ボットを構築する

このリポジトリをフォークするだけで、GitHub Actions 上でサーバーレスに動く Discord 追跡通知ボットが手に入ります。

### 仕組み

```
GitHub Actions (毎時 cron)
  → scripts/check.py が全登録番号をスクレイプ
  → 前回のハッシュと比較
  → 変化あり → Discord Webhook で通知
  → data/trackings.json を自動 commit
```

### セットアップ（3ステップ）

#### 1. フォーク

このリポジトリを Fork します。

#### 2. Discord Webhook を設定

1. Discord サーバーの通知先チャンネル → **設定 → 連携サービス → ウェブフック**
2. **新しいウェブフック** を作成し URL をコピー
3. フォークしたリポジトリの **Settings → Secrets and variables → Actions** で追加:
   - **Name**: `DISCORD_WEBHOOK_URL`
   - **Value**: コピーした Webhook URL

#### 3. Actions の書き込み権限を有効化

**Settings → Actions → General → Workflow permissions** で **Read and write permissions** を選択して保存。

これで完了です。以降、追跡番号を登録すれば1時間おきに自動チェックされ、変化があれば Discord に通知が届きます。

### 追跡番号の登録・削除

GitHub リポジトリの **Actions** タブから操作します。

| 操作 | 手順 |
|---|---|
| **登録** | Actions → `Register Tracking Number` → Run workflow → 番号入力 → アクション `register` |
| **削除** | 同上 → アクション `remove` |
| **手動チェック** | Actions → `Check Tracking Updates` → Run workflow |

### Discord 通知イメージ

```
🚚 配送状況が更新されました: 1234567890123

商品種別: クリックポスト

2026/03/10 12:26
引受
○○郵便局 (東京都) 〒100-0001

2026/03/11 06:33
到着
△△郵便局 (大阪府) 〒530-0001
```

---

## ファイル構成

```
japanpost_tracker/         # pip install 可能なパッケージ
  __init__.py
  scraper.py               # コアのスクレイピングロジック
api/
  tracking.py              # Vercel Serverless API エンドポイント
scripts/
  check.py                 # GitHub Actions 用 CLI
  requirements.txt
data/
  trackings.json           # 追跡データ（自動更新）
.github/workflows/
  register.yml             # 追跡番号の登録・削除
  check.yml                # 1時間ごとの定期チェック
pyproject.toml             # パッケージ設定
```

## API エンドポイント（Vercel）

Vercel にデプロイすると HTTP API としても使えます。

```bash
# 1件取得
curl "https://your-app.vercel.app/api/tracking?number=1234567890123"

# 複数取得（カンマ区切り）
curl "https://your-app.vercel.app/api/tracking?number=1234567890123,123456789012"
```

デプロイ:
```bash
npm i -g vercel
vercel login
vercel --prod
```

## License

MIT
