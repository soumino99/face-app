document.addEventListener("DOMContentLoaded", () => {
  const screens = document.querySelectorAll(".screen");
  const cameraVideo = document.getElementById("camera");
  const featureCanvas = document.getElementById("feature-canvas");
  const resultCanvas = document.getElementById("result-canvas");
  const shootButton = document.querySelector(".shoot-button");
  const goFeatureButton = document.getElementById("go-feature");
  const diagnoseButton = document.getElementById("start-diagnosis");
  const retryAnalysisButton = document.getElementById("retry-analysis");
  const resultTypeEl = document.getElementById("result-type");
  const resultDescriptionEl = document.getElementById("result-description");
  const resultCelebrityEl = document.getElementById("result-celebrity");
  const resultPaletteEl = document.getElementById("result-palette");
  const resultCareEl = document.getElementById("result-care");
  const resultNextEl = document.getElementById("result-next");
  const API_BASE_URL = "/api"; // same origin served by FastAPI

  let cameraStream = null;
  let capturedImageData = null;
  let currentLandmarks = [];
  let analysisId = null;
  let featureImage = null;
  let isDraggingPoint = false;
  let dragPointIndex = -1;
  let activePointerId = null;

  const showScreen = (id) => {
    screens.forEach((screen) => {
      screen.classList.toggle("active", screen.id === id);
    });

    if (id === "screen-camera") {
      startCamera();
    }
  };

  async function startCamera() {
    if (cameraStream || !cameraVideo) {
      return;
    }

    if (!navigator.mediaDevices?.getUserMedia) {
      alert("このブラウザはカメラに対応していません");
      return;
    }

    try {
      cameraStream = await navigator.mediaDevices.getUserMedia({
        audio: false,
        video: { facingMode: "user" },
      });
      cameraVideo.srcObject = cameraStream;
    } catch (error) {
      console.error(error);
      alert("カメラを起動できませんでした");
    }
  }

  function capturePhoto() {
    if (!cameraVideo?.videoWidth) {
      alert("カメラの準備ができていません");
      return;
    }

    const canvas = document.createElement("canvas");
    canvas.width = cameraVideo.videoWidth;
    canvas.height = cameraVideo.videoHeight;
    const ctx = canvas.getContext("2d");
    ctx.translate(canvas.width, 0);
    ctx.scale(-1, 1);
    ctx.drawImage(cameraVideo, 0, 0, canvas.width, canvas.height);
    capturedImageData = canvas.toDataURL("image/jpeg");

    const preview = document.querySelector("#screen-confirm .image-preview");
    if (preview) {
      preview.innerHTML = `<img src="${capturedImageData}" style="width:100%; border-radius: 16px;" alt="captured" />`;
    }

    analysisId = null;
    currentLandmarks = [];
  }

  function base64ToBlob(dataUrl) {
    const base64 = dataUrl.split(",")[1];
    const binary = atob(base64);
    const len = binary.length;
    const buffer = new Uint8Array(len);
    for (let i = 0; i < len; i += 1) {
      buffer[i] = binary.charCodeAt(i);
    }
    return new Blob([buffer], { type: "image/jpeg" });
  }

  function loadFeatureImage(imageData) {
    if (!featureCanvas) return;
    featureImage = new Image();
    featureImage.onload = () => {
      renderFeatureCanvas();
    };
    featureImage.src = imageData;
  }

  function renderFeatureCanvas(highlightIndex = -1) {
    if (!featureCanvas) return;
    const ctx = featureCanvas.getContext("2d");
    if (featureImage) {
      featureCanvas.width = featureImage.width;
      featureCanvas.height = featureImage.height;
      ctx.clearRect(0, 0, featureCanvas.width, featureCanvas.height);
      ctx.drawImage(featureImage, 0, 0);
    } else {
      ctx.clearRect(0, 0, featureCanvas.width, featureCanvas.height);
    }

    ctx.lineWidth = 2;
    currentLandmarks.forEach((point, index) => {
      ctx.beginPath();
      ctx.fillStyle = index === highlightIndex ? "#00a1ff" : "#ff4d6d";
      ctx.strokeStyle = "#ffffff";
      ctx.arc(point.x, point.y, index === highlightIndex ? 7 : 5, 0, Math.PI * 2);
      ctx.fill();
      ctx.stroke();
    });
  }

  function showLandmarksWithImage(imageData) {
    loadFeatureImage(imageData);
    setTimeout(() => renderFeatureCanvas(), 60);
  }

  async function sendImageToServerForFaceDetect() {
    if (!capturedImageData) {
      alert("先に撮影してください");
      return;
    }

    showScreen("screen-loading");
    const formData = new FormData();
    formData.append("file", base64ToBlob(capturedImageData), "photo.jpg");

    try {
      const response = await fetch(`${API_BASE_URL}/face-analyze`, {
        method: "POST",
        body: formData,
      });

      if (!response.ok) {
        throw new Error("face analyze failed");
      }

      const data = await response.json();
      currentLandmarks = data.landmarks ?? [];
      analysisId = data.analysisId;
      showLandmarksWithImage(capturedImageData);
      showScreen("screen-feature");
    } catch (error) {
      console.error(error);
      alert("顔解析に失敗しました");
      showScreen("screen-confirm");
    }
  }

  async function sendLandmarksForDiagnosis() {
    if (!analysisId) {
      alert("解析情報がありません。先に特徴点解析を行ってください。");
      return;
    }

    showScreen("screen-loading");
    try {
      const response = await fetch(`${API_BASE_URL}/diagnose`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          analysisId,
          landmarks: currentLandmarks,
        }),
      });

      if (!response.ok) {
        throw new Error("diagnose failed");
      }

      const data = await response.json();
      renderDiagnosisResult(data.result);
      displayResultImage();
      showScreen("screen-result");
    } catch (error) {
      console.error(error);
      alert("診断に失敗しました");
      showScreen("screen-feature");
    }
  }

  function renderDiagnosisResult(result) {
    if (!result) {
      return;
    }
    if (resultTypeEl) {
      resultTypeEl.textContent = result.type ?? "結果を取得できませんでした";
    }
    if (resultDescriptionEl) {
      resultDescriptionEl.textContent = result.description ?? "";
    }
    if (resultCelebrityEl) {
      resultCelebrityEl.textContent = result.celebrity
        ? `似ている有名人: ${result.celebrity}`
        : "";
    }
    renderChipList(resultPaletteEl, result.palette);
    renderList(resultCareEl, result.careTips);
    renderList(resultNextEl, result.nextSteps);
  }

  function renderChipList(container, items) {
    if (!container) return;
    container.innerHTML = "";
    if (!Array.isArray(items) || !items.length) {
      return;
    }
    items.forEach((text) => {
      const chip = document.createElement("span");
      chip.className = "chip";
      chip.textContent = text;
      container.appendChild(chip);
    });
  }

  function renderList(container, items) {
    if (!container) return;
    container.innerHTML = "";
    if (!Array.isArray(items) || !items.length) {
      return;
    }
    items.forEach((text) => {
      const li = document.createElement("li");
      li.textContent = text;
      container.appendChild(li);
    });
  }

  function displayResultImage() {
    if (!capturedImageData || !resultCanvas) {
      return;
    }

    const ctx = resultCanvas.getContext("2d");
    const img = new Image();
    img.src = capturedImageData;
    img.onload = () => {
      resultCanvas.width = img.width;
      resultCanvas.height = img.height;
      ctx.drawImage(img, 0, 0);
    };
  }

  document.addEventListener("click", (event) => {
    const button = event.target.closest("[data-target]");
    if (!button) {
      return;
    }
    showScreen(button.getAttribute("data-target"));
  });

  featureCanvas?.addEventListener("pointerdown", handleCanvasPointerDown);
  featureCanvas?.addEventListener("pointermove", handleCanvasPointerMove);
  featureCanvas?.addEventListener("pointerup", handleCanvasPointerUp);
  featureCanvas?.addEventListener("pointerleave", handleCanvasPointerUp);
  featureCanvas?.addEventListener("dblclick", handleCanvasDoubleClick);

  shootButton?.addEventListener("click", capturePhoto);
  goFeatureButton?.addEventListener("click", () => sendImageToServerForFaceDetect());
  diagnoseButton?.addEventListener("click", () => sendLandmarksForDiagnosis());
  retryAnalysisButton?.addEventListener("click", () => sendImageToServerForFaceDetect());

  showScreen("screen-home");

  function handleCanvasPointerDown(event) {
    if (!featureCanvas || !currentLandmarks.length) return;
    const { x, y } = getCanvasCoordinates(event);
    const index = findNearbyPointIndex(x, y);
    if (index === -1) {
      return;
    }
    isDraggingPoint = true;
    dragPointIndex = index;
    featureCanvas.setPointerCapture(event.pointerId);
    activePointerId = event.pointerId;
    renderFeatureCanvas(dragPointIndex);
  }

  function handleCanvasPointerMove(event) {
    if (!isDraggingPoint || dragPointIndex === -1 || !featureCanvas) return;
    const { x, y } = getCanvasCoordinates(event);
    currentLandmarks[dragPointIndex] = {
      x: clamp(x, 0, featureCanvas.width),
      y: clamp(y, 0, featureCanvas.height),
    };
    renderFeatureCanvas(dragPointIndex);
  }

  function handleCanvasPointerUp() {
    if (isDraggingPoint && featureCanvas && activePointerId !== null) {
      try {
        featureCanvas.releasePointerCapture(activePointerId);
      } catch (error) {
        console.debug("Pointer capture release skipped", error);
      }
    }
    isDraggingPoint = false;
    dragPointIndex = -1;
    activePointerId = null;
    renderFeatureCanvas();
  }

  function handleCanvasDoubleClick(event) {
    if (!featureCanvas) return;
    const { x, y } = getCanvasCoordinates(event);
    currentLandmarks.push({ x, y });
    renderFeatureCanvas(currentLandmarks.length - 1);
  }

  function getCanvasCoordinates(event) {
    const rect = featureCanvas.getBoundingClientRect();
    const scaleX = featureCanvas.width / rect.width;
    const scaleY = featureCanvas.height / rect.height;
    return {
      x: (event.clientX - rect.left) * scaleX,
      y: (event.clientY - rect.top) * scaleY,
    };
  }

  function findNearbyPointIndex(x, y) {
    const threshold = 15;
    for (let i = currentLandmarks.length - 1; i >= 0; i -= 1) {
      const point = currentLandmarks[i];
      const distance = Math.hypot(point.x - x, point.y - y);
      if (distance <= threshold) {
        return i;
      }
    }
    return -1;
  }

  function clamp(value, min, max) {
    return Math.min(Math.max(value, min), max);
  }
});
