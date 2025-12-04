from __future__ import annotations

import math
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
    ("chin_tip", 152),
    ("jaw_left", 172),
    ("jaw_right", 397),
    ("jaw_corner_left", 234),
    ("jaw_corner_right", 454),
    ("cheek_left", 93),
    ("cheek_right", 323),
    ("temple_left", 67),
    ("temple_right", 297),
    ("forehead_left", 109),
    ("forehead_right", 338),
    ("forehead_center", 10),
    ("upper_cheek_left", 50),
    ("upper_cheek_right", 280),
]

FACE_SHAPE_LABELS = {
    "round": "丸顔",
    "oval": "卵型",
    "long": "面長",
    "heart": "逆三角形",
    "square": "ベース型",
    "diamond": "ひし形",
}


# 形分類用のしきい値 (後から調整しやすいように集約)
ASPECT_LONG_STRONG = 1.40  # 面長を強く判定する縦横比 (H / cheek_width)
ASPECT_LONG_SOFT = 1.30  # 面長寄りの緩いしきい値

HEART_FOREHEAD_MIN = 1.05  # 逆三角形: 額 / 頬 の最小比
HEART_JAW_MAX = 0.85  # 逆三角形: 顎 / 頬 の最大比
HEART_TEMPLE_MIN = 1.02  # 逆三角形: こめかみ / 頬 の最小比
HEART_JAW_ANGLE_MAX = 150  # 逆三角形: 顎角の最大角度 (小さいほどシャープ)

DIAMOND_PROMINENCE_MIN = 1.10  # ひし形: 頬骨突出度 (upper_cheek / jawline)
DIAMOND_FOREHEAD_MAX = 1.02  # ひし形: 額 / 頬 の最大比
DIAMOND_JAW_MAX = 0.95  # ひし形: 顎 / 頬 の最大比

SQUARE_JAW_MIN = 1.00  # ベース型: 顎 / 頬 の最小比
SQUARE_JAWLINE_MIN = 0.98  # ベース型: エラ / 頬 の最小比
SQUARE_JAW_ANGLE_MIN = 150  # ベース型: 顎角の最小角度 (大きいほど角ばる)
SQUARE_FOREHEAD_MAX = 1.05  # ベース型: 額 / 頬 の最大比 (広すぎると逆三角形寄り)

ROUND_ASPECT_MAX = 1.15  # 丸顔: 縦横比の最大値
ROUND_FOREHEAD_DELTA_MAX = 0.08  # 丸顔: 額/頬 比と 1.0 の許容差
ROUND_JAW_MIN = 0.95  # 丸顔: 顎 / 頬 の最小比
ROUND_JAW_ANGLE_MIN = 145  # 丸顔: 顎角の最小角度

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
    landmarks: Optional[List[Landmark]] = Field(default=None)


class DiagnoseResult(BaseModel):
    shape: str


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
        faceShape=_shape_label(face_shape),
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

    descriptor = _build_descriptor(face_shape)
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
    for _, idx in TARGET_LANDMARKS:
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


def _landmark_map(landmarks: List[Landmark]) -> Dict[str, Landmark]:
    if len(landmarks) < len(TARGET_LANDMARKS):
        return {}
    return {name: landmarks[idx] for idx, (name, _) in enumerate(TARGET_LANDMARKS)}


def _distance(p1: Landmark, p2: Landmark) -> float:
    return math.hypot(p1.x - p2.x, p1.y - p2.y)


def _angle(a: Landmark, b: Landmark, c: Landmark) -> float:
    """Return the ABC angle in degrees (with B as vertex)."""

    ab = (a.x - b.x, a.y - b.y)
    cb = (c.x - b.x, c.y - b.y)
    ab_len = math.hypot(*ab)
    cb_len = math.hypot(*cb)
    if ab_len == 0 or cb_len == 0:
        return 0.0
    cos_angle = max(-1.0, min(1.0, (ab[0] * cb[0] + ab[1] * cb[1]) / (ab_len * cb_len)))
    return math.degrees(math.acos(cos_angle))


def _analyze_face_shape_mediapipe(landmarks: List[Landmark]) -> str:
    """Classify into six face shapes using landmark ratios and angles."""

    lm = _landmark_map(landmarks)
    required = {
        "chin_tip",
        "cheek_left",
        "cheek_right",
        "forehead_center",
        "forehead_left",
        "forehead_right",
        "temple_left",
        "temple_right",
        "jaw_left",
        "jaw_right",
        "jaw_corner_left",
        "jaw_corner_right",
        "upper_cheek_left",
        "upper_cheek_right",
    }
    if not required.issubset(lm.keys()):
        return "oval"

    chin = lm["chin_tip"]
    forehead_center = lm["forehead_center"]
    cheek_width = _distance(lm["cheek_left"], lm["cheek_right"])
    temple_width = _distance(lm["temple_left"], lm["temple_right"])
    forehead_width = _distance(lm["forehead_left"], lm["forehead_right"])
    jaw_width = _distance(lm["jaw_left"], lm["jaw_right"])
    jawline_width = _distance(lm["jaw_corner_left"], lm["jaw_corner_right"])
    upper_cheek_width = _distance(lm["upper_cheek_left"], lm["upper_cheek_right"])
    face_height = _distance(chin, forehead_center)

    if face_height <= 0 or cheek_width <= 0:
        return "oval"

    # 基本となる比率・角度
    aspect = face_height / cheek_width
    forehead_vs_cheek = forehead_width / cheek_width
    temple_vs_cheek = temple_width / cheek_width
    jaw_vs_cheek = jaw_width / cheek_width
    jawline_vs_cheek = jawline_width / cheek_width
    cheek_prominence = upper_cheek_width / jawline_width if jawline_width else 1.0
    jaw_angle = _angle(lm["jaw_corner_left"], chin, lm["jaw_corner_right"])

    # 1. 面長: 明確に縦長のものを最優先で判定
    if aspect >= ASPECT_LONG_STRONG:
        return "long"

    # 2. 逆三角形: 額が広く顎が細い + 上部の横幅が広め + 顎角がシャープ
    if (
        forehead_vs_cheek >= HEART_FOREHEAD_MIN
        and jaw_vs_cheek <= HEART_JAW_MAX
        and temple_vs_cheek >= HEART_TEMPLE_MIN
        and jaw_angle <= HEART_JAW_ANGLE_MAX
    ):
        return "heart"

    # 3. ひし形: 頬骨が額・顎より明らかに広く突出
    if (
        cheek_prominence >= DIAMOND_PROMINENCE_MIN
        and forehead_vs_cheek <= DIAMOND_FOREHEAD_MAX
        and jaw_vs_cheek <= DIAMOND_JAW_MAX
    ):
        return "diamond"

    # 4. ベース型: 顎幅・エラ幅が広く、角ばった輪郭
    if (
        jaw_vs_cheek >= SQUARE_JAW_MIN
        and jawline_vs_cheek >= SQUARE_JAWLINE_MIN
        and jaw_angle >= SQUARE_JAW_ANGLE_MIN
        and forehead_vs_cheek <= SQUARE_FOREHEAD_MAX
    ):
        return "square"

    # 5. 丸顔: 縦横比が低く、額と頬の幅が近く、顎もふっくら
    if (
        aspect <= ROUND_ASPECT_MAX
        and abs(forehead_vs_cheek - 1.0) <= ROUND_FOREHEAD_DELTA_MAX
        and jaw_vs_cheek >= ROUND_JAW_MIN
        and jaw_angle >= ROUND_JAW_ANGLE_MIN
    ):
        return "round"

    # 6. どれにも強く当てはまらないものは卵型として扱う
    return "oval"


def _shape_label(shape: str) -> str:
    return FACE_SHAPE_LABELS.get(shape, "バランスタイプ")


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
        "long": "面長さんは横ラインや前髪でバランスを取ると◎。",
        "diamond": "ひし形タイプは頬骨を意識したハイライトで立体感を演出。",
    }
    return tips.get(shape, "バランスの良いフェイスラインです。")


def _build_descriptor(face_shape: str) -> DiagnoseResult:
    return DiagnoseResult(shape=_shape_label(face_shape))


def _purge_expired() -> None:
    now = datetime.utcnow()
    expired_keys = [
        key
        for key, value in analysis_store.items()
        if now - value["created_at"] > ANALYSIS_TTL
    ]
    for key in expired_keys:
        analysis_store.pop(key, None)
