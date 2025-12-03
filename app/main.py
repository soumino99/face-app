from __future__ import annotations

import random
from datetime import datetime, timedelta
from hashlib import sha256
from pathlib import Path
from typing import Dict, List, Optional
from uuid import uuid4

import cv2
import mediapipe as mp
import numpy as np
from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field

MAX_FILE_BYTES = 5 * 1024 * 1024  # 5MB
ANALYSIS_TTL = timedelta(minutes=30)

BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"
TEMPLATES_DIR = BASE_DIR / "templates"

app = FastAPI(title="Face Diagnosis App", version="0.2.0")

mp_face_mesh = mp.solutions.face_mesh
face_mesh = mp_face_mesh.FaceMesh(
    max_num_faces=1,
    min_detection_confidence=0.5,
    min_tracking_confidence=0.5,
)

TARGET_LANDMARKS = [
    152,  # chin tip
    127,
    356,
    226,
    446,
    1,
    61,
    291,
]

templates = Jinja2Templates(directory=str(TEMPLATES_DIR))
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class Landmark(BaseModel):
    x: float = Field(..., ge=0)
    y: float = Field(..., ge=0)


class FaceAnalyzeResponse(BaseModel):
    analysisId: str
    landmarks: List[Landmark]
    quality: dict
    faceShape: str
    symmetry: dict
    recommendationPreview: str


class DiagnoseInput(BaseModel):
    analysisId: str = Field(..., min_length=10)
    stylePreference: Optional[str] = Field(default=None)
    focus: Optional[str] = Field(default=None)
    landmarks: Optional[List[Landmark]] = Field(default=None)


class DiagnoseResult(BaseModel):
    type: str
    description: str
    palette: List[str]
    celebrity: str
    careTips: List[str]
    nextSteps: List[str]


class DiagnoseResponse(BaseModel):
    result: DiagnoseResult


analysis_store: Dict[str, dict] = {}


@app.get("/", response_class=HTMLResponse)
async def serve_index(request: Request) -> HTMLResponse:
    return templates.TemplateResponse("index.html", {"request": request})


@app.get("/api/health")
async def health() -> dict:
    return {"status": "ok", "timestamp": datetime.utcnow().isoformat()}


@app.post("/api/face-analyze", response_model=FaceAnalyzeResponse)
async def face_analyze(file: UploadFile = File(...)) -> FaceAnalyzeResponse:
    if file.content_type not in {"image/jpeg", "image/png", "image/webp"}:
        raise HTTPException(status_code=400, detail="対応していないファイル形式です")

    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="ファイルが空です")
    if len(content) > MAX_FILE_BYTES:
        raise HTTPException(
            status_code=413, detail="ファイルサイズが大きすぎます (上限5MB)"
        )

    try:
        image = _load_image(content)
        rgb_image = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
    except Exception as exc:  # pragma: no cover - invalid input
        raise HTTPException(
            status_code=400, detail="画像の読み込みに失敗しました"
        ) from exc

    results = face_mesh.process(rgb_image)
    landmarks: List[Landmark] = []
    if results.multi_face_landmarks:
        face_landmarks = results.multi_face_landmarks[0]
        landmarks = _normalize_mediapipe_landmarks(
            face_landmarks, image.shape[1], image.shape[0]
        )

    if not landmarks:
        raise HTTPException(
            status_code=400,
            detail="顔を検出できませんでした。正面を向いて明るい場所で撮影してください。",
        )

    face_shape = _analyze_face_shape_mediapipe(landmarks)
    quality_score = _calculate_quality(image)
    quality_label = _quality_label(quality_score)
    symmetry_score = _calculate_symmetry_mediapipe(landmarks)
    fingerprint = int(sha256(content).hexdigest()[:8], 16)

    analysis_id = str(uuid4())
    analysis_store[analysis_id] = {
        "created_at": datetime.utcnow(),
        "landmarks": [lm.model_dump() for lm in landmarks],
        "quality": {"score": quality_score, "label": quality_label},
        "face_shape": face_shape,
        "symmetry": {"score": symmetry_score, "label": _symmetry_label(symmetry_score)},
        "fingerprint": fingerprint,
    }
    _purge_expired()

    return FaceAnalyzeResponse(
        analysisId=analysis_id,
        landmarks=landmarks,
        quality={"score": quality_score, "message": f"撮影状態: {quality_label}"},
        faceShape=face_shape,
        symmetry={"score": symmetry_score, "label": _symmetry_label(symmetry_score)},
        recommendationPreview=_face_shape_tip(face_shape),
    )


@app.post("/api/diagnose", response_model=DiagnoseResponse)
async def diagnose(payload: DiagnoseInput) -> DiagnoseResponse:
    analysis = analysis_store.get(payload.analysisId)
    if not analysis:
        raise HTTPException(status_code=404, detail="解析セッションが見つかりません")

    if payload.landmarks:
        analysis["landmarks"] = [lm.model_dump() for lm in payload.landmarks]

    face_shape = analysis["face_shape"]
    style_pref = (payload.stylePreference or "natural").lower()
    focus = (payload.focus or "balance").lower()

    descriptor = _build_descriptor(face_shape, style_pref, focus)
    return DiagnoseResponse(result=descriptor)


def _symmetry_label(score: float) -> str:
    if score >= 0.85:
        return "シンメトリー◎"
    if score >= 0.7:
        return "バランス良好"
    return "左右差あり"


def _load_image(content: bytes) -> np.ndarray:
    arr = np.frombuffer(content, np.uint8)
    image = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if image is None:
        raise ValueError("invalid image data")
    return image


def _normalize_mediapipe_landmarks(
    face_landmarks, width: int, height: int
) -> List[Landmark]:
    normalized: List[Landmark] = []
    for idx in TARGET_LANDMARKS:
        if idx >= len(face_landmarks.landmark):
            continue
        lm = face_landmarks.landmark[idx]
        normalized.append(
            Landmark(
                x=round(lm.x * width, 2),
                y=round(lm.y * height, 2),
            )
        )
    return normalized


def _analyze_face_shape_mediapipe(landmarks: List[Landmark]) -> str:
    if len(landmarks) < 3:
        return "oval"
    left = landmarks[1]
    right = landmarks[2]
    chin = landmarks[0]
    width = abs(right.x - left.x)
    height = abs(chin.y - (left.y + right.y) / 2)
    if width <= 0 or height <= 0:
        return "oval"
    aspect_ratio = width / height
    if aspect_ratio > 1.5:
        return "round"
    if aspect_ratio < 1.1:
        return "heart"
    return "oval"


def _calculate_quality(image: np.ndarray) -> float:
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    blur_score = cv2.Laplacian(gray, cv2.CV_64F).var()
    focus_score = min(1.0, blur_score / 500.0)
    brightness_score = min(1.0, np.mean(gray) / 170.0)
    return round(0.5 * focus_score + 0.5 * brightness_score, 2)


def _quality_label(score: float) -> str:
    if score >= 0.85:
        return "とても鮮明"
    if score >= 0.7:
        return "十分な明るさ"
    return "少し暗め"


def _calculate_symmetry_mediapipe(landmarks: List[Landmark]) -> float:
    return round(0.7 + random.random() * 0.2, 2)


def _face_shape_tip(shape: str) -> str:
    tips = {
        "oval": "オーバル輪郭は万能タイプ。前髪で印象調整がしやすいです。",
        "round": "丸顔さんは縦ラインを意識するとシャープに見えます。",
        "heart": "逆三角形はトップにボリュームを出すと華やかさアップ。",
        "square": "ベース型は柔らかいカールでフェイスラインをカバー。",
    }
    return tips.get(shape, "バランスの良いフェイスラインです。")


def _build_descriptor(face_shape: str, style_pref: str, focus: str) -> DiagnoseResult:
    palette_options = {
        "natural": ["コーラルピンク", "ミルクティーベージュ", "ローズブラウン"],
        "cool": ["ライラック", "アッシュグレー", "ネイビーブラック"],
        "cute": ["ピーチピンク", "アプリコット", "ハニーオレンジ"],
    }
    celebrity_map = {
        "oval": "〇〇 さん風の上品さ",
        "round": "△△ さんのような柔らかさ",
        "heart": "◇◇ さんの華やかライン",
        "square": "□□ さんの知的ムード",
    }
    care_tips = {
        "eyes": ["アイラインは目尻をやや長めに", "下まつげは軽めに"],
        "line": ["チークは耳下から斜めに", "シェーディングでフェイスラインを整える"],
        "balance": [
            "眉とリップの色味を合わせる",
            "トップスは曲線的なネックラインがおすすめ",
        ],
    }
    shape_titles = {
        "oval": "ノーブルバランス",
        "round": "ソフトキュート",
        "heart": "フェミニンブリリアント",
        "square": "モードエレガンス",
    }

    palette = palette_options.get(style_pref, palette_options["natural"])
    focus_key = focus if focus in care_tips else "balance"
    title = f"{shape_titles.get(face_shape, 'スタンダード')} × {style_pref.title()}"
    description = _build_description(face_shape, style_pref)

    return DiagnoseResult(
        type=title,
        description=description,
        palette=palette,
        celebrity=celebrity_map.get(face_shape, "親しみやすい印象"),
        careTips=care_tips[focus_key],
        nextSteps=[
            "照明の良い場所で再撮影するとスコアが安定します",
            "おすすめカラーでメイクや服を試してみてください",
            "気に入った結果はスクリーンショットで保存しましょう",
        ],
    )


def _build_description(face_shape: str, style_pref: str) -> str:
    shape_desc = {
        "oval": "バランスの取れた輪郭で、どの角度から見ても整った印象です。",
        "round": "柔らかく親しみやすい雰囲気が強く、笑顔が映えるタイプです。",
        "heart": "キリッとした目元とシャープな顎先が特徴で、華やかさが際立ちます。",
        "square": "直線的な骨格がクールで知的な印象を与えます。",
    }
    style_desc = {
        "natural": "ナチュラルカラーで透明感を引き出すと◎",
        "cool": "寒色系で洗練されたムードを演出できます。",
        "cute": "温かみのある色味でフェミニンに仕上がります。",
    }
    return f"{shape_desc.get(face_shape, '整ったバランスタイプです。')}{style_desc.get(style_pref, '')}"


def _purge_expired() -> None:
    now = datetime.utcnow()
    expired_keys = [
        key
        for key, value in analysis_store.items()
        if now - value["created_at"] > ANALYSIS_TTL
    ]
    for key in expired_keys:
        analysis_store.pop(key, None)
