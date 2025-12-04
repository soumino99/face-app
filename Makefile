# face-app 用 make ターゲット
UV ?= uv
UV_PROJECT_ENVIRONMENT ?= .venv
APP ?= app.main:app
HOST ?= 0.0.0.0
PORT ?= 8000
DOCKER_IMAGE ?= face-app
DOCKER_CONTAINER ?= face-app
DOCKER_HOST_PORT ?= 8000

export UV_PROJECT_ENVIRONMENT

.PHONY: venv install run clean docker-build docker-run docker-stop

# 仮想環境が無いときだけ生成
venv: $(UV_PROJECT_ENVIRONMENT)/pyvenv.cfg

$(UV_PROJECT_ENVIRONMENT)/pyvenv.cfg:
	$(UV) venv $(UV_PROJECT_ENVIRONMENT)

# uv で依存パッケージをインストール
install: venv requirements.txt
	$(UV) pip install -r requirements.txt

# uv 経由で FastAPI 開発サーバー起動
run: install
	$(UV) run uvicorn $(APP) --reload --host $(HOST) --port $(PORT)

# 仮想環境を削除して初期化
clean:
	rm -rf $(UV_PROJECT_ENVIRONMENT)

# Docker イメージをビルド
docker-build: Dockerfile requirements.txt
	docker build -t $(DOCKER_IMAGE) .

# Docker コンテナを起動
docker-run: docker-build
	docker run --rm -p $(DOCKER_HOST_PORT):$(PORT) --name $(DOCKER_CONTAINER) $(DOCKER_IMAGE)

# Docker コンテナを停止
docker-stop:
	-docker stop $(DOCKER_CONTAINER)
