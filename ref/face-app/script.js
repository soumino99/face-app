// ========= 画面切り替え =========
const screens = document.querySelectorAll(".screen");

function showScreen(id) {
  screens.forEach((screen) => {
    screen.classList.toggle("active", screen.id === id);
  });

  // カメラ画面に来たときだけカメラ起動
  if (id === "screen-camera") {
    startCamera();
  }
}

// data-target を持つボタンで画面遷移
document.addEventListener("click", (event) => {
  const btn = event.target.closest("[data-target]");
  if (!btn) return;

  const targetId = btn.getAttribute("data-target");
  showScreen(targetId);
});

// 最初はホーム画面
showScreen("screen-home");

// ========= カメラプレビュー部分 =========
let cameraStream = null;

async function startCamera() {
  // すでに起動済みなら何もしない
  if (cameraStream) return;

  if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
    alert("このブラウザはカメラに対応していません");
    return;
  }

  const video = document.getElementById("camera");
  if (!video) return;

  const constraints = {
    audio: false,
    video: {
      facingMode: "user", // インカメラを使用
    },
  };

  try {
    const stream = await navigator.mediaDevices.getUserMedia(constraints);
    cameraStream = stream;
    video.srcObject = stream;
  } catch (err) {
    console.error(err);
    alert("カメラが使えませんでした：" + err.message);
  }
}

// ===== 診断開始ボタン用：ロード画面を挟む =====

function showLoadingThen(nextId, delayMs = 1000) {
  // ロード画面を表示
  showScreen("screen-loading");

  // 今はダミーで一定時間待つ（本番ではここで解析処理を行う）
  setTimeout(() => {
    showScreen(nextId);
  }, delayMs);
}

/*
// 実際に処理を書くときの例（メモ用）
async function runFaceAnalysis() {
  // ここに顔認識処理などを書く
  await new Promise((resolve) => setTimeout(resolve, 3000));
}

async function showLoadingThen(nextId) {
  showScreen("screen-loading");
  await runFaceAnalysis();
  showScreen(nextId);
}
*/

// data-loading-target を持つボタンでロード → 遷移
const loadingButtons = document.querySelectorAll("[data-loading-target]");

loadingButtons.forEach((btn) => {
  btn.addEventListener("click", () => {
    const nextId = btn.getAttribute("data-loading-target");
    showLoadingThen(nextId);
  });
});