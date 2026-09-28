"""轨道交通信号检修管理平台 后端服务入口。

启动：./run.sh（先做启动前自检再起服务）
健康检查：GET /api/health —— 除存活外还返回依赖与初始化数据的自检明细，
         自检不过时 ok=false 并指出是哪一项。
"""
from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.bootstrap import run_checks
from app.config import settings
from app.routers import ROUTERS
from app.store import store

app = FastAPI(title="轨道交通信号检修管理平台", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

for module in ROUTERS:
    app.include_router(module.router)


@app.get("/api/health")
def health() -> dict[str, object]:
    """健康检查：服务存活 + 依赖/初始化数据自检结果。

    自检失败时仍返回 200（服务本身在运行），通过 ok=false 与 checks 明细
    指出是依赖缺失还是初始化数据问题，避免监控把两类问题混为一谈。
    """
    report = run_checks()
    return {
        "ok": report["ok"],
        "app": settings.app_name,
        "env": settings.env,
        "modules": len(store.module_names()),
        "checks": report["checks"],
    }


@app.get("/api/overview")
def overview() -> dict[str, object]:
    """运营概览：把各业务模块的待处理量汇总成看板卡片。"""
    return store.overview()
