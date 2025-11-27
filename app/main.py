from __future__ import annotations

from datetime import datetime, timedelta
from hashlib import sha256
from pathlib import Path
from typing import Dict, List, Optional
from uuid import uuid4

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

    fingerprint = int(sha256(content).hexdigest()[:8], 16)
    rng = _seeded_rng(fingerprint)
    landmarks = _generate_landmarks(rng)

    quality_score = round(0.55 + rng.random() * 0.4, 2)
    quality_label = (
        "とても鮮明"
        if quality_score >= 0.85
        else ("十分な明るさ" if quality_score >= 0.7 else "少し暗め")
    )
    face_shape = _pick_from(rng, ["oval", "round", "heart", "square"])
    symmetry_score = round(0.5 + rng.random() * 0.5, 2)

    analysis_id = str(uuid4())
    analysis_store[analysis_id] = {
        "created_at": datetime.utcnow(),
        "landmarks": landmarks,
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


def _seeded_rng(seed: int):
    import random

    return random.Random(seed)


def _generate_landmarks(rng) -> List[dict]:
    points = []
    base_x = rng.randint(80, 160)
    base_y = rng.randint(120, 200)
    for idx in range(12):
        points.append(
            {
                "x": base_x + rng.randint(-30, 120) + idx * 5,
                "y": base_y + rng.randint(-20, 120) + idx * 3,
            }
        )
    return points


def _pick_from(rng, items: List[str]) -> str:
    return items[int(rng.random() * len(items))]


def _symmetry_label(score: float) -> str:
    if score >= 0.85:
        return "シンメトリー◎"
    if score >= 0.7:
        return "バランス良好"
    return "左右差あり"


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
