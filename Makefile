.PHONY: install backend frontend init check test build clean

# 一次装好：后端按锁定版本装依赖（run.sh 会自建/修复 venv），前端按锁文件安装
install:
	cd backend && PYTHON_BIN=python3 ./run.sh --install-only
	cd frontend && npm ci || npm install

# 后端（日志落 backend/logs/backend.log）
backend:
	cd backend && ./run.sh

frontend:
	cd frontend && npm run dev

# 防雷元件：幂等初始化（重复执行不清已有测试记录）
init:
	cd backend && .venv/bin/python -m app.bootstrap

# 防雷元件：自检（失败退出码非 0；区分依赖缺失与数据缺失）
check:
	cd backend && .venv/bin/python -m app.bootstrap --check

# 后端单元测试
test:
	cd backend && .venv/bin/python -m unittest discover -s tests -v

# 前端构建产物固定输出到 frontend/dist/
build:
	cd frontend && npm run build

clean:
	rm -rf backend/var backend/logs frontend/dist
