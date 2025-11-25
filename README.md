# 顔診断アプリ

FastAPI がフロントエンド（HTML/CSS/JS）と API をまとめて配信するシンプルな構成。

## ディレクトリ構成

```
face-app-2/
├─ app/
│  ├─ main.py              # FastAPI エントリーポイントと API 定義
│  ├─ templates/
│  │  └─ index.html        # 既存デザインの HTML（Jinja2 で配信）
│  └─ static/
│     ├─ style.css
│     ├─ script.js
│     └─ img/
│        └─ camera-icon.png
├─ requirements.txt        # 依存パッケージ
└─ README.md
```

## 必要環境

- Python 3.11 以上（3.10 でも動作可）
- PowerShell（Windows 標準）
- （任意）パッケージマネージャー [uv](https://github.com/astral-sh/uv)

## セットアップ手順（標準的な `pip` 利用）

```powershell
python -m venv .venv
.\.venv\Scripts\activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

## セットアップ手順（uv を使う場合・任意）

```powershell
uv venv .venv
.\.venv\Scripts\activate
uv pip install -r requirements.txt
```

## 開発サーバーの起動

```powershell
.\.venv\Scripts\activate
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

- ブラウザで `http://127.0.0.1:8000/` を開くとアプリ画面が表示され、`/static` 配下の CSS/JS も同じ FastAPI プロセスから配信されます。

## API エンドポイント

| メソッド | パス           | 説明                                                         |
|----------|----------------|--------------------------------------------------------------|
| POST     | `/face-detect` | `multipart/form-data` で画像を受け取り、ダミー特徴点を返却 |
| POST     | `/diagnose`    | `{ "landmarks": [{"x":..,"y":..}, ...] }` を受け取り結果を返却 |

## 動作確認のポイント

1. 画面のボタン操作で撮影 → 確認 → 特徴点表示 → 診断結果まで遷移できること。
2. 開発者ツール Network タブで `/static/...` へのリクエストが 200 で返ること。
3. API 単体確認が必要なら別端末から `curl` で下記のように呼び出し。
  ```powershell
  curl -X POST http://127.0.0.1:8000/diagnose -H "Content-Type: application/json" -d '{"landmarks":[{"x":1,"y":2}]}'
  ```

## 補足

- 静的ファイルは FastAPI の `StaticFiles` で提供しているため、追加のフロント用ビルドやサーバーは不要。
- ブラウザのカメラ権限は `localhost` では許可されますが、別ホスト名を使う場合は HTTPS か適切な権限設定が必要。
