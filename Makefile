.PHONY: install backend frontend init selfcheck test logs

install: ## 一次装好前后端依赖
	cd backend && python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
	cd frontend && npm install

init: ## 幂等初始化：只补齐缺失记录，不清掉已有的测试记录
	cd backend && .venv/bin/python -m app.bootstrap init

selfcheck: ## 启动前自检：区分依赖缺失(2)/数据缺失(3)/防雷样例不全(4)
	cd backend && .venv/bin/python -m app.bootstrap selfcheck

test: ## 后端单元测试（初始化幂等性 + 自检分类）
	cd backend && .venv/bin/python -m unittest discover -s tests

backend: ## 启动后端（先自检，日志在 backend/logs/backend.log）
	cd backend && ./run.sh

frontend: ## 启动前端
	cd frontend && npm run dev

build-frontend: ## 前端构建产物固定输出到 frontend/dist/
	cd frontend && npm run build

logs: ## 跟踪后端日志
	tail -f backend/logs/backend.log
