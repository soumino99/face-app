# 顔診断アプリ（仕様リファレンス）

カメラ撮影から診断結果提示までを 1 ページで完結させるシングルページアプリ。

## アーキテクチャ概要

- **フロントエンド**: `app/templates/index.html` + `app/static/{style.css,script.js,img/...}`。Vanilla JS で各画面を制御し、API とは Fetch API で通信。
- **バックエンド**: FastAPI (`app/main.py`) が HTML/静的ファイル/REST API を統合提供。`uvicorn` で起動。
- **データフロー**: 撮影画像 → `/api/face-analyze` が MediaPipe Face Mesh でランドマーク/品質/輪郭タイプを算出 → 特徴点を表示・微調整 → `/api/diagnose` へ解析ID＋嗜好を送信 → 推奨タイプを返却。

## ディレクトリ構成

```
face-app/
├─ app/
│  ├─ main.py              # FastAPI エントリーポイントと API 定義
│  ├─ templates/
│  │  └─ index.html        # 固定デザインの HTML（Jinja2 で配信）
│  └─ static/
│     ├─ style.css         # 既存 UI デザイン
│     ├─ script.js         # 画面遷移と API コールを管理
│     └─ img/
│        └─ camera-icon.png
├─ requirements.txt
└─ README.md
```

## フロントエンド仕様

### 画面一覧（デザインは既存 CSS を流用）

| ID | 表示名 | 主な要素 | 遷移トリガー |
|----|--------|----------|--------------|
| G-1 | ホーム | タイトル、`診断スタート` | `診断スタート` → G-2 |
| G-2 | カメラ撮影 | `<video id="camera">`、撮影ボタン、戻るボタン | 撮影 → G-2-1、戻る → G-1 |
| G-2-1 | 撮影確認 | 撮影した静止画プレビュー、`次へ` / `撮り直す` | `撮り直す` → G-2、`次へ` → G-L → G-3 |
| G-3 | 特徴点確認 | `<canvas id="feature-canvas">`、解析サマリー、嗜好セレクト、`再認識`、`診断開始` | `再認識` → `/api/face-analyze` 再実行、`診断開始` → G-L → G-4 |
| G-L | ローディング | スピナー、`Loading…` | API 呼び出し中のみ一時表示 |
| G-4 | 診断結果 | `<canvas id="result-canvas">`、結果タイプ/説明、カラーパレット、ケア/次のアクション、再診断ボタン | `もう一度診断` → G-2、`アプリ終了` → G-1 |

### フロントエンド処理フロー

1. **カメラ起動**: `startCamera()` が `navigator.mediaDevices.getUserMedia()` で前面カメラを取得。ストリームは `cameraStream` にキャッシュ。
2. **撮影と保存**: `capturePhoto()` で `<video>` を canvas に転写し、左右反転を補正した Base64 (`capturedImageData`) を保持。
3. **特徴点リクエスト**: `sendImageToServerForFaceDetect()` が Base64 → Blob 変換後 `FormData` として `/api/face-analyze` へ送信。バックエンドは MediaPipe Face Mesh (FaceMesh, max_num_faces=1) で 8 点の主要ランドマーク（顎先/頬骨/目頭/鼻先/口角）を抽出し、レスポンスで `analysisId` と `landmarks` を返す。ユーザーは描画された点をドラッグで微調整できる。
4. **診断リクエスト**: `sendLandmarksForDiagnosis()` が `analysisId` とユーザーが調整した `landmarks` を JSON で `/api/diagnose` に送信。結果は従来どおり結果画面で表示し、撮影画像を `result-canvas` に再描画。
5. **UI 状態管理**: `.screen` 要素に `active` クラス付与で表示切替。`data-target` 属性を持つボタンで遷移し、ローディング時は `screen-loading` を共通表示。

### ブラウザ要件

- HTTPS or `localhost` でのアクセス（カメラ権限のため）。
- Chrome/Edge/Safari 最新版を想定。iOS/Android でも動作するよう `playsinline` と `muted` を設定済み。

## API 仕様（v2）

| エンドポイント | メソッド | リクエスト | 成功レスポンス | エラー例 |
|----------------|----------|------------|-----------------|----------|
| `/api/face-analyze` | POST | `multipart/form-data` で `file` (画像: JPEG/PNG/WebP、上限 5MB) | `200 OK` `{ "analysisId", "landmarks" (MediaPipe 8点), "quality", "faceShape", "symmetry", "recommendationPreview" }` | `400` 形式エラー、`413` サイズ超過 |
| `/api/diagnose` | POST | `application/json` `{ "analysisId": string, "stylePreference"?: "natural"\|"cool"\|"cute", "focus"?: "balance"\|"eyes"\|"line", "landmarks"?: Landmark[] }` | `200 OK` `{ "result": { "type", "description", "palette", "celebrity", "careTips", "nextSteps" } }` | `404` 解析ID不明、`422` バリデーション | *UI では `stylePreference`/`focus` は送信していませんが API としては利用可能* |
| `/api/health` | GET | なし | `200 OK` `{ "status": "ok", "timestamp": "..." }` | - |

### データモデル例

```jsonc
FaceAnalyzeResponse {
  "analysisId": "uuid",
  "landmarks": [{"x": 140.1, "y": 210.5}, ...],
  "quality": {"score": 0.82, "message": "撮影状態: 十分な明るさ"},
  "faceShape": "oval",
  "symmetry": {"score": 0.77, "label": "バランス良好"},
  "recommendationPreview": "..."
}

DiagnoseResponse {
  "result": {
    "type": "ノーブルバランス × Natural",
    "description": "...",
    "palette": ["コーラルピンク", "ミルクティーベージュ"],
    "celebrity": "〇〇 さん風の上品さ",
    "careTips": ["..."],
    "nextSteps": ["..."]
  }
}

DiagnoseRequest {
  "analysisId": "uuid",
  "landmarks": [{"x": 150.0, "y": 200.0}, ...],
  "stylePreference": "natural",   // 必要に応じてAPIで直接指定可能
  "focus": "eyes"
}
```

### バリデーション / セキュリティ方針

- MIME タイプは `image/jpeg|png|webp` のみ許容。アップロード上限は 5MB。
- 解析セッション (`analysisId`) は 30 分で破棄されるため、診断 API は同セッション内で呼び出す。
- CORS は開発中 `allow_origins=["*"]`。運用時は `https://{your-domain}` のみに限定。
- 認証は実装していないため、公開 API にする場合は API キーやレート制限の追加が推奨。

## セットアップ（pip）

```powershell
python -m venv .venv
.\.venv\Scripts\activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

## セットアップ（uv 利用）

```powershell
uv venv .venv
.\.venv\Scripts\activate
uv pip install -r requirements.txt
```

## 開発サーバー起動

```powershell
.\.venv\Scripts\activate
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

- `http://127.0.0.1:8000/` にアクセスすると SPA と静的ファイルが同じプロセスから提供される。

## 動作確認チェックリスト

1. ボタン操作で G-1 → G-4 まで遷移し、撮影画像と結果が表示される。
2. 特徴点画面で MediaPipe が自動打点したポイントをドラッグして微調整できる。
3. 開発者ツール Network タブで `/static/...`、`/api/face-analyze`、`/api/diagnose` が 200 を返している。
4. API 単体テスト例:
  ```powershell
  # 先に face-analyze を叩き、analysisId を取得してから使用
  curl -X POST http://127.0.0.1:8000/api/diagnose ^
    -H "Content-Type: application/json" ^
    -d '{"analysisId":"<face-analyzeで取得したID>","stylePreference":"natural"}'
  ```

## 運用上の注意

- 静的ファイルは FastAPI の `StaticFiles` が配信するためビルド不要。ただしキャッシュ制御を行いたい場合はリバースプロキシ側で設定。
- カメラを利用するため、公開 URL は必ず HTTPS にすること（Render や Vercel などのマネージドサービスで解決可能）。
- 画像処理を実装する際は、アップロードファイルの保存先とライフサイクル（即削除 or 一時保存）を別途設計。
