# japanpost-tracker

日本郵便・ヤマト運輸の追跡番号をスクレイプして配送状況を取得する Python ライブラリ & Discord 通知ボット。

GitHub Actions だけで動くサーバーレス構成。追跡番号を登録すると1時間おきに配送状況をチェックし、変化があれば Discord に通知します。

```
GitHub Actions (cron: 毎時0分)
  ↓
scripts/check.py (Python スクレイピング)
  ↓
日本郵便 or ヤマト運輸の追跡ページをスクレイプ
  ↓
data/trackings.json と比較
  ↓ 変化あり
Discord Webhook で通知
  ↓
data/trackings.json を更新 & git commit
```

### 対応キャリア

| キャリア | キャリアID | 追跡元 |
|---|---|---|
| 日本郵便 | `japanpost` | trackings.post.japanpost.jp |
| ヤマト運輸 | `yamato` | toi.kuronekoyamato.co.jp |

---

## ライブラリとして使う（pip install）

誰でも `pip install` するだけで追跡情報を取得できます。

### インストール

```bash
pip install git+https://github.com/hirorogo/japanpost-tracker.git
```

### 基本的な使い方

```python
from japanpost_tracker import track, track_yamato

# 日本郵便
result = track("1234567890123")

# ヤマト運輸
result = track_yamato("123456789012")

print(result.latest_status)    # "引受" / "配達完了"
print(result.carrier)          # "japanpost" / "yamato"
print(result.carrier_name)     # "日本郵便" / "ヤマト運輸"
print(result.product_type)     # "クリックポスト" / "ヤマト運輸"
print(result.is_delivered)     # False
print(result.url)              # 追跡ページURL

# 全履歴を取得
for entry in result.entries:
    print(f"{entry.date} | {entry.status} | {entry.office}")

# JSON として出力
print(result.to_json())

# dict に変換
data = result.to_dict()
```

### 複数番号を一括取得

```python
from japanpost_tracker import track_multi, track_yamato_multi, TrackingError

# 日本郵便
results = track_multi(["1234567890123", "123456789012"])

# ヤマト運輸
results = track_yamato_multi(["123456789012", "098765432109"])

for r in results:
    if isinstance(r, TrackingError):
        print(f"Error: {r}")
    else:
        print(f"[{r.carrier_name}] {r.tracking_number}: {r.latest_status}")
```

### エラーハンドリング

```python
from japanpost_tracker import track, track_yamato, TrackingError

try:
    result = track("000000000000")
except TrackingError as e:
    print(f"取得失敗: {e}")

try:
    result = track_yamato("000000000000")
except TrackingError as e:
    print(f"取得失敗: {e}")
```

### 返却データ

| プロパティ | 型 | 説明 |
|---|---|---|
| `tracking_number` | `str` | 追跡番号 |
| `carrier` | `str` | キャリアID（`japanpost` / `yamato`） |
| `carrier_name` | `str` | キャリア名（日本郵便 / ヤマト運輸） |
| `product_type` | `str` | 商品種別（ゆうパック、クリックポスト等） |
| `entries` | `list[TrackingEntry]` | 配送履歴リスト |
| `contacts` | `list[ContactOffice]` | 問い合わせ窓口局 |
| `latest_status` | `str \| None` | 最新ステータス |
| `latest_entry` | `TrackingEntry \| None` | 最新の履歴エントリ |
| `is_delivered` | `bool` | 配達完了フラグ |
| `entries_hash` | `str` | 履歴の SHA256 ハッシュ（変化検出用） |
| `url` | `str` | 追跡ページURL |
| `checked_at` | `str` | 取得日時 (ISO 8601) |

---

## フォークして Discord 通知ボットを構築する

このリポジトリをフォークするだけで、GitHub Actions 上でサーバーレスに動く Discord 追跡通知ボットが手に入ります。

### 仕組み

```
GitHub Actions (毎時 cron)
  → scripts/check.py が全登録番号をスクレイプ
  → キャリアごとに適切な追跡ページを参照
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
| **登録** | Actions → `Register Tracking Number` → Run workflow → 番号入力 → 配送業者選択（`japanpost` / `yamato`） → アクション `register` |
| **削除** | 同上 → アクション `remove` |
| **手動チェック** | Actions → `Check Tracking Updates` → Run workflow |

### Discord 通知イメージ

```
[日本郵便] 配送状況が更新されました: 1234567890123

商品種別: クリックポスト

2026/03/10 12:26
引受
○○郵便局 (東京都) 〒100-0001

2026/03/11 06:33
到着
△△郵便局 (大阪府) 〒530-0001
```

```
[ヤマト運輸] 配送状況が更新されました: 123456789012

商品種別: ヤマト運輸

03/10 12:00
荷物受付
○○センター
```

---

## TimeTree ↔ Google Calendar 双方向同期

TimeTree と Google Calendar を自動で双方向同期する機能です。GitHub Actions で15分ごとに動作します。

### 仕組み

```
GitHub Actions (cron: 15分ごと)
  ↓
scripts/calendar_sync.py
  ↓
TimeTree API / Google Calendar API から予定を取得
  ↓
未同期の予定を相手側に作成（名前の末尾に「douki」を付与）
  ↓ 変更あり
変更された側の内容をもう片方に反映
  ↓
data/sync_mappings.json を更新 & git commit
```

- **新規予定**: 片方に予定を作ると、もう片方にも `予定名 douki` として自動作成
- **変更反映**: 片方の予定を編集すると、次回同期時にもう片方へ反映
- **削除反映**: 片方の予定を消すと、もう片方も自動削除
- **競合解決**: 両方で同時に変更された場合は、更新日時が新しい方を優先

### セットアップ

#### 1. TimeTree アクセストークンの取得

1. [TimeTree Developer](https://developers.timetreeapp.com/) にログイン
2. **パーソナルアクセストークン** を発行
3. 同期したいカレンダーの **カレンダーID** を取得

#### 2. Google サービスアカウントの作成

1. [Google Cloud Console](https://console.cloud.google.com/) でプロジェクトを作成
2. **Google Calendar API** を有効化
3. **サービスアカウント** を作成し、JSON キーをダウンロード
4. 同期先の Google カレンダーの共有設定で、サービスアカウントのメールアドレスに **編集権限** を付与

#### 3. GitHub Secrets を設定

フォークしたリポジトリの **Settings → Secrets and variables → Actions** で以下を追加:

| Secret 名 | 説明 |
|---|---|
| `TIMETREE_ACCESS_TOKEN` | TimeTree パーソナルアクセストークン |
| `TIMETREE_CALENDAR_ID` | 同期対象の TimeTree カレンダーID |
| `GOOGLE_CREDENTIALS_JSON` | サービスアカウントの認証情報 JSON（ファイルの中身をそのまま貼る） |
| `GOOGLE_CALENDAR_ID` | 同期先の Google カレンダーID（省略時は `primary`） |

設定後、Actions タブから `Calendar Sync` ワークフローを手動実行して動作確認できます。

### ローカルで実行

```bash
pip install requests google-api-python-client google-auth

export TIMETREE_ACCESS_TOKEN="your-token"
export TIMETREE_CALENDAR_ID="your-calendar-id"
export GOOGLE_CREDENTIALS_JSON='{"type":"service_account",...}'
export GOOGLE_CALENDAR_ID="primary"

python scripts/calendar_sync.py
```

---

## ファイル構成

```
japanpost_tracker/         # pip install 可能なパッケージ
  __init__.py
  scraper.py               # 日本郵便スクレイピング & 共通データクラス
  yamato_scraper.py         # ヤマト運輸スクレイピング
api/
  tracking.py              # Vercel Serverless API エンドポイント
scripts/
  check.py                 # GitHub Actions 用 CLI（追跡）
  calendar_sync.py         # TimeTree ↔ Google Calendar 同期
  requirements.txt
data/
  trackings.json           # 追跡データ（自動更新）
  sync_mappings.json       # カレンダー同期マッピング（自動更新）
.github/workflows/
  register.yml             # 追跡番号の登録・削除
  check.yml                # 1時間ごとの定期チェック
  calendar_sync.yml        # 15分ごとのカレンダー同期
pyproject.toml             # パッケージ設定
```

## API エンドポイント（Vercel）

Vercel にデプロイすると HTTP API としても使えます。

```bash
# 日本郵便（デフォルト）
curl "https://your-app.vercel.app/api/tracking?number=1234567890123"

# ヤマト運輸
curl "https://your-app.vercel.app/api/tracking?number=123456789012&carrier=yamato"

# 複数取得（カンマ区切り）
curl "https://your-app.vercel.app/api/tracking?number=1234567890123,123456789012&carrier=japanpost"
```

デプロイ:
```bash
npm i -g vercel
vercel login
vercel --prod
```

## License

MIT
