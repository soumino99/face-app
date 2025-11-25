from pathlib import Path
from typing import List

from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"
TEMPLATES_DIR = BASE_DIR / "templates"

app = FastAPI(title="Face Diagnosis App", version="0.1.0")

templates = Jinja2Templates(directory=str(TEMPLATES_DIR))
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class Landmark(BaseModel):
    x: float
    y: float


class LandmarksInput(BaseModel):
    landmarks: List[Landmark]


@app.get("/", response_class=HTMLResponse)
async def serve_index(request: Request) -> HTMLResponse:
    return templates.TemplateResponse("index.html", {"request": request})


@app.post("/face-detect")
async def face_detect(file: UploadFile = File(...)) -> dict:
    if file.content_type not in {"image/jpeg", "image/png", "image/webp"}:
        raise HTTPException(status_code=400, detail="Unsupported file type")

    dummy_landmarks = [
        {"x": 120, "y": 200},
        {"x": 150, "y": 210},
        {"x": 180, "y": 220},
        {"x": 200, "y": 250},
        {"x": 220, "y": 280},
    ]
    return {"landmarks": dummy_landmarks}


@app.post("/diagnose")
async def diagnose(data: LandmarksInput) -> dict:
    count = len(data.landmarks)
    if count <= 2:
        result = "Type-A"
    elif count <= 4:
        result = "Type-B"
    else:
        result = "Type-C"

    return {"result": result}
