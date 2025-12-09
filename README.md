# 顔診断アプリ

カメラ撮影またはライブラリからの画像選択で顔を取り込み、MediaPipe Face Mesh から抽出したランドマークをもとに 6 タイプの輪郭（丸顔 / 卵型 / 面長 / 逆三角形 / ベース型 / ひし形）を判定するシングルページアプリです。FastAPI が SPA・静的ファイル・REST API をまとめて提供します。

## クイックスタート

### 1. uv / make でローカル実行

```powershell
git clone <repo>
cd face-app
uv venv .venv
.\.venv\Scripts\activate
uv pip install -r requirements.txt
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

`make install` → `make run` でも同じ流れで起動できます。`make clean` で仮想環境を削除します。

ブラウザで `http://127.0.0.1:8000/` を開き、カメラ権限を許可するか、ライブラリアイコンを押して任意の画像を選択してください。HTTPS もしくは `localhost` であれば iOS/Android Safari/Chrome でも動作します。

### 2. Docker でローカル実行

```powershell
docker build -t face-app .
docker run --rm -p 8000:8000 face-app
```

別ポートで公開したい場合は `-p <host_port>:8000` を変更してください。Make には `docker-build` / `docker-run` / `docker-stop` ターゲットも用意しています。

```powershell
make docker-build
make docker-run DOCKER_HOST_PORT=8080  # 例: ホスト側を 8080 にする
# 終了時
make docker-stop
```

## Render へのデプロイ

Render では Docker サービスを選択すると、`Dockerfile` に記述した Python 3.10 + 依存パッケージ構成でデプロイできます。

1. このリポジトリを GitHub/GitLab にプッシュ。
2. Render ダッシュボード → **New +** → **Web Service** → 対象リポジトリを選択。
3. **Environment** を `Docker` に設定し、**Root Directory** は `.` のまま。Build Command/Start Command は空で OK（`Dockerfile` の CMD が使われます）。
4. 必要に応じて `PORT=8000` など追加環境変数を設定し、デプロイ開始。

公開後は Render 側で HTTPS が有効になるため、スマホブラウザからでもカメラ権限が許可されます。

## フロントエンド概要

- `app/templates/index.html` … SPA 本体。`screen-*` のセクション切り替えで状態管理。
- `app/static/script.js` … Vanilla JS。以下を担当:
  - カメラ起動 (`navigator.mediaDevices.getUserMedia`) と撮影処理。
  - ライブラリ選択（`<input type="file">`）からの Base64 変換。
  - 解析済みランドマークの描画・ドラッグ編集 (`<canvas id="feature-canvas">`)。
  - `/api/face-analyze` / `/api/diagnose` との通信。
- `app/static/style.css` … PC/モバイル両対応のシンプルなデザイン。アップロードボタンは `library-icon.png` を用いたリファレンス準拠のデザイン。

### 画面フロー

1. **ホーム (G-1)** – 診断スタートボタン。
2. **カメラ/ライブラリ選択 (G-2)** – カメラプレビュー + 丸型撮影ボタン + ライブラリアイコン。
3. **確認 (G-2-1)** – 撮影/選択した画像の確認と再撮影。
4. **特徴点確認 (G-3)** – ランドマーク描画、再認識、診断開始ボタン。
5. **ローディング (G-L)** – API 呼び出し中に挿入。
6. **診断結果 (G-4)** – 撮影画像と最終的な輪郭ラベルのみをシンプルに表示。

## バックエンド概要

- `app/main.py`
  - FastAPI でエンドポイントとテンプレート/静的ファイルを提供。
  - MediaPipe Face Mesh（`max_num_faces=1`）を初期化し、解析結果を 30 分間 `analysis_store` に保持。
  - ランドマークは 14 点（顎先/顎角/頬骨/額/こめかみ 等）を抽出し、距離・角度比を用いた輪郭分類ロジック `_analyze_face_shape_mediapipe` で 6 タイプを判定。
  - 結果レスポンスは最終的な日本語ラベルのみ（例: `"丸顔"`）。

### API 仕様

| Endpoint | Method | Request | Response (200) | 備考 |
|----------|--------|---------|----------------|------|
| `/api/face-analyze` | POST | `multipart/form-data` で `file` (JPEG/PNG/WebP, ≤5MB) | `{ analysisId, landmarks, quality, faceShape, symmetry, recommendationPreview }` | `landmarks` は 14 点のピクセル座標。`faceShape`/`recommendationPreview` は自動判定結果。 |
| `/api/diagnose` | POST | `application/json` `{ analysisId, landmarks? }` | `{ result: { shape } }` | 解析済みセッション ID を入力。ランドマークを再送すればサーバー側ストアが上書きされる。 |
| `/api/health` | GET | – | `{ status, timestamp }` | ヘルスチェック用 |

**レスポンス例**

```jsonc
// /api/face-analyze
{
  "analysisId": "e5bb...",
  "landmarks": [{"x":140.1,"y":210.5}, ...],
  "quality": {"score":0.82,"message":"撮影状態: 十分な明るさ"},
  "faceShape": "面長",
  "symmetry": {"score":0.74,"label":"バランス良好"},
  "recommendationPreview": "面長さんは横ラインや前髪でバランスを取ると◎。"
}

// /api/diagnose
{ "result": { "shape": "面長" } }
```

### ランドマークセット

| キー | MediaPipe idx | 意味 |
|------|---------------|------|
| chin_tip | 152 | 顎先 |
| jaw_left / jaw_right | 172 / 397 | 下顎ライン |
| jaw_corner_left / right | 234 / 454 | エラ部分 |
| cheek_left / right | 93 / 323 | 頬骨中央 |
| upper_cheek_left / right | 50 / 280 | 頬骨上部 |
| temple_left / right | 67 / 297 | こめかみ |
| forehead_left / right | 109 / 338 | 額幅 |
| forehead_center | 10 | 額中央 |

各距離を顔の高さで正規化し、額/頬/顎幅・頬骨の突出度・顎角度を条件に 6 クラスへ分類しています。

### 顔型判定ロジック（Mermaid フローチャート）

```mermaid
flowchart TD
    S[顔画像入力・ランドマーク抽出]
    S --> N1{顔の高さで正規化済みの
      額幅・頬幅・顎幅・頬骨突出度・顎角度を計算}
    N1 --> N2{顎幅/顔高 < 0.32}
    N2 -- Yes --> N3{頬幅/顔高 < 0.36}
    N2 -- No  --> N6{顎角度 > 130°}
    N3 -- Yes --> R1[丸顔]
    N3 -- No  --> N4{額幅 ≈ 頬幅 ≈ 顎幅}
    N4 -- Yes --> R2[卵型]
    N4 -- No  --> N5{顔高/顔幅 > 1.4}
    N5 -- Yes --> R3[面長]
    N5 -- No  --> R4[ひし形]
    N6 -- Yes --> R5[ベース型]
    N6 -- No  --> R6[逆三角形]
```

**凡例**
- 額幅/頬幅/顎幅: 額・頬・顎の横幅（ランドマーク間距離）
- 顔高: 顎先〜額中央の距離
- 頬骨突出度: 頬骨中央の横幅
- 顎角度: 顎角ランドマーク間の角度

※実際の閾値や条件はコード（`_analyze_face_shape_mediapipe`）で微調整されています。

## 開発メモ

- `Makefile` を用意済み: `make venv`, `make install`, `make run`, `make clean`。
- uv/pip どちらでも依存解決可能だが、既定では `.venv` を前提に uv を推奨。
- カメラアイコンはインライン SVG、ライブラリアイコンは `library-icon.png` を参照（いずれも `app/templates/index.html` から変更可能）。
- iOS/Android でカメラを使用する場合は必ず HTTPS でデプロイすること。

## 動作確認チェックリスト

1. PC/スマホで `診断スタート` → カメラ表示/ライブラリ選択が機能する。
2. 撮影 or 画像選択 → `次へ` で確認画面、`診断開始` でランドマークが描画される。
3. `/api/face-analyze` が `200` を返し、結果画面に日本語ラベル（丸顔など）が表示される。
4. 開発者ツール Network タブで `/static/*` と API のレスポンスを確認。
5. 必要に応じて `curl` でヘルスチェック: `curl http://127.0.0.1:8000/api/health`。

## 運用時の注意点

- 静的ファイルは FastAPI の `StaticFiles` で配信。キャッシュ制御はリバースプロキシ側で設定する。
- `analysis_store` はメモリ保持なので、スケールアウト時は共有セッションストア（Redis 等）を検討。
- 顔画像はメモリ上でのみ処理し永続化しない設計。必要ならアップロードディレクトリとライフサイクルを設けること。
- カメラ API は HTTPS でないとモバイルブラウザからブロックされるので、本番は必ず TLS を有効化。
