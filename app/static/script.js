document.addEventListener("DOMContentLoaded", () => {
  const screens = document.querySelectorAll(".screen");
  const cameraVideo = document.getElementById("camera");
  const featureCanvas = document.getElementById("feature-canvas");
  const resultCanvas = document.getElementById("result-canvas");
  const shootButton = document.querySelector(".shoot-button");
  const goFeatureButton = document.getElementById("go-feature");
  const diagnoseButton = document.getElementById("start-diagnosis");
  const resultText = document.getElementById("result-text");
  const loadingButtons = document.querySelectorAll("[data-loading-target]");
  const API_BASE_URL = ""; // same origin served by FastAPI

  let cameraStream = null;
  let capturedImageData = null;
  let currentLandmarks = [];

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

  function drawImageOnCanvas(imageDataUrl, canvas) {
    if (!canvas) {
      return;
    }
    const ctx = canvas.getContext("2d");
    const img = new Image();
    img.onload = () => {
      canvas.width = img.width;
      canvas.height = img.height;
      ctx.drawImage(img, 0, 0);
    };
    img.src = imageDataUrl;
  }

  function drawLandmarks(canvas, landmarks) {
    if (!canvas) {
      return;
    }
    const ctx = canvas.getContext("2d");
    ctx.fillStyle = "red";
    ctx.strokeStyle = "red";
    ctx.lineWidth = 2;
    landmarks.forEach((point) => {
      ctx.beginPath();
      ctx.arc(point.x, point.y, 4, 0, Math.PI * 2);
      ctx.fill();
    });
  }

  function showLandmarksWithImage(imageData, landmarks) {
    drawImageOnCanvas(imageData, featureCanvas);
    setTimeout(() => drawLandmarks(featureCanvas, landmarks), 60);
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
      const response = await fetch(`${API_BASE_URL}/face-detect`, {
        method: "POST",
        body: formData,
      });

      if (!response.ok) {
        throw new Error("face detect failed");
      }

      const data = await response.json();
      currentLandmarks = data.landmarks ?? [];
      showLandmarksWithImage(capturedImageData, currentLandmarks);
      showScreen("screen-feature");
    } catch (error) {
      console.error(error);
      alert("顔認識に失敗しました");
      showScreen("screen-confirm");
    }
  }

  async function sendLandmarksForDiagnosis() {
    if (!currentLandmarks.length) {
      alert("特徴点を取得できていません");
      return;
    }

    showScreen("screen-loading");
    try {
      const response = await fetch(`${API_BASE_URL}/diagnose`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ landmarks: currentLandmarks }),
      });

      if (!response.ok) {
        throw new Error("diagnose failed");
      }

      const data = await response.json();
      resultText.textContent = data.result ?? "結果が取得できませんでした";
      displayResultImage();
      showScreen("screen-result");
    } catch (error) {
      console.error(error);
      alert("診断に失敗しました");
      showScreen("screen-feature");
    }
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

  loadingButtons.forEach((button) => {
    button.addEventListener("click", () => {
      const nextId = button.getAttribute("data-loading-target");
      showScreen("screen-loading");
      setTimeout(() => showScreen(nextId), 1000);
    });
  });

  shootButton?.addEventListener("click", capturePhoto);
  goFeatureButton?.addEventListener("click", () => sendImageToServerForFaceDetect());
  diagnoseButton?.addEventListener("click", () => sendLandmarksForDiagnosis());

  showScreen("screen-home");
});
