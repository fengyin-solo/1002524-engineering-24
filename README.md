# 轨道交通信号检修管理平台

面向轨道交通信号设备日常巡检、故障处置、天窗修作业、器材检修与联锁试验的一体化信号检修管理后台。

这是一个前后端分离的管理平台：前端 Vue 3 + Vite + TypeScript，后端 FastAPI（Python）。
两边各自独立启动，前端 dev server 已关掉自动打开页面，启动后按终端打印的地址手工打开。

## 目录结构

```text
.
├── frontend/                 Vue 3 + Vite + TypeScript 前端
│   ├── src/views/            每个业务模块一个页面
│   ├── src/api/              统一请求封装
│   ├── src/stores/           会话与筛选状态
│   ├── dist/                 前端构建产物（npm run build 输出，git 忽略）
│   └── vite.config.ts        dev server 配置（open: false）
├── backend/                  FastAPI（Python） 后端
│   ├── app/routers/          每个业务模块一组接口
│   ├── app/services/         业务规则与状态流转
│   ├── app/store.py          内存数据仓库（按 id 幂等合并初始化数据）
│   ├── app/bootstrap.py      启动前自检 / 幂等初始化（python -m app.bootstrap）
│   ├── data/seed.json        本地与线上共用的唯一一份初始化数据
│   ├── tests/                初始化幂等性与自检分类测试
│   ├── logs/                 运行日志 backend.log（git 忽略）
│   └── run.sh                自检 → 幂等初始化 → 起服务
├── .env.example              环境变量样例（复制为 .env 后按需改）
├── .gitignore
└── docker-compose.yml
```

## 环境要求（按文档一次装好）

- Python 3.11+（含 venv；Debian/Ubuntu 若提示 ensurepip 不可用，先 `sudo apt install python3-venv`）
- Node.js 20+、npm 10+
- Make（可选，只是把下面的命令封装了一下）

### 一键安装依赖

```bash
make install
# 不用 make 时：
# cd backend && python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
# cd frontend && npm install
```

后端依赖版本在 `backend/requirements.txt` 里钉死，前端锁定文件随仓库提供，
因此换一台机器装出来的版本一致。

## 初始化数据（本地与线上共用一份）

唯一数据源是 `backend/data/seed.json`，本地开发和容器镜像都读它，**不要再在代码或本地文件里手改数据**。
防雷元件（`lightning`）固定 4 条记录，覆盖三种测试情形：

| id | 元件编号 | 情形 | 关键字段 |
| --- | --- | --- | --- |
| 1 | LIGH-0001 | 防护有效（正常基线） | 泄露电流 12 μA、动作次数 0 |
| 2 | LIGH-0002 | **泄露电流超标** | 泄露电流 86 μA、状态 `泄露超标` |
| 3 | LIGH-0003 | **动作频繁** | 动作次数 17、状态 `动作频繁` |
| 4 | LIGH-0004 | **已更换** | 更换记录含日期，复测合格、状态 `已更换` |

初始化是**幂等**的：按 `模块 + id` 只补齐缺失记录，已存在的记录（含运行中改过的测试记录）
不覆盖、不删除。重复执行 `init` 第二次新增数为 0。

```bash
make init        # cd backend && .venv/bin/python -m app.bootstrap init
```

## 启动前自检（分清是数据缺失还是依赖没装好）

```bash
make selfcheck   # cd backend && .venv/bin/python -m app.bootstrap selfcheck
```

自检逐项检查运行依赖、初始化数据文件、防雷元件三种情形是否齐全，失败时退出码含义固定：

| 退出码 | 含义 | 处理办法 |
| --- | --- | --- |
| 0 | 全部通过 | — |
| 2 | **依赖没装好** | `.venv/bin/pip install -r requirements.txt` |
| 3 | **初始化数据缺失/损坏** | 确认 `backend/data/seed.json` 存在且是合法 JSON |
| 4 | 防雷元件样例不全 | seed.json 的 lightning 需含泄露超标/动作频繁/已更换三种情形 |

服务启动后 `GET /api/health` 也返回同样的自检明细（`ok` 与每项 `checks`），可直接作为部署探针。

### 后端

```bash
make backend     # 或 cd backend && ./run.sh
```

`run.sh` 会先建/更新 venv、跑幂等初始化与自检，自检不过就不启动并打印对应退出码的说明。
健康检查：`curl http://127.0.0.1:8000/api/health`

### 前端

```bash
make frontend    # 或 cd frontend && npm run dev
```

前端默认监听 `http://127.0.0.1:5173/`，dev server 不会自动打开浏览器，
需要自己访问。`/api` 由 vite 代理到后端 `http://127.0.0.1:8000`。

## 构建产物与运行日志的约定位置

| 内容 | 位置 | 说明 |
| --- | --- | --- |
| 后端运行日志 | `backend/logs/backend.log` | run.sh 同时输出到终端和该文件；容器内挂载同名目录 |
| 前端构建产物 | `frontend/dist/` | `make build-frontend`（即 `npm run build`）固定输出到这里 |
| 后端虚拟环境 | `backend/.venv/` | 不入库，换机重建；不要从别的机器拷贝 |
| 初始化数据 | `backend/data/seed.json` | 入库，是本地与线上共用的唯一一份 |

## 换机重新部署

初始化数据与依赖版本都在仓库里，换机后跑出来的防雷元件数据一致：

```bash
make install      # 装依赖（版本锁定）
make init         # 幂等初始化，已有测试记录不受影响
make selfcheck    # 应全部 PASS
make backend      # 起服务
```

容器方式：`docker compose up --build`。后端容器启动前同样执行一次 `bootstrap init`，
镜像内置同一份 `data/seed.json`，compose 用 `/api/health` 做健康检查，日志挂载到 `backend/logs/`。

## 测试

```bash
make test         # cd backend && .venv/bin/python -m unittest discover -s tests
```

覆盖：重复初始化不清/不覆盖已有测试记录、只补齐缺失 id、自检对“依赖缺失 vs 数据缺失”的
分类与退出码、防雷元件三种情形与必填字段。测试只验证初始化与自检，不涉及业务规则本身。

## 业务模块

| 模块 | 目录 | 业务对象 | 主要字段 |
| --- | --- | --- | --- |
| 联锁管理 | `interlock` | 联锁道岔 | 道岔编号、所属车站、道岔类型 |
| 轨道电路 | `trackcircuit` | 轨道电路 | 区段编号、所属区间、载频类型 |
| 信号机 | `signal` | 信号机 | 信号机编号、所属车站、信号机类型 |
| 转辙机 | `pointmachine` | 转辙机 | 转辙机编号、所属道岔、转辙机型号 |
| 信号电缆 | `cable` | 信号电缆 | 电缆编号、起止站点、电缆芯数 |
| 信号电源 | `powersupply` | 电源屏 | 电源屏编号、所属车站、输入电压 |
| 车载设备 | `atp` | 车载ATP | 设备编号、所属列车、设备型号 |
| 应答器 | `balise` | 应答器 | 应答器编号、所在位置、报文版本 |
| 计轴设备 | `axlecounter` | 计轴器 | 计轴器编号、所属区间、检测磁头 |
| 调度中心 | `dispatchcenter` | 调度台 | 调度台编号、管辖范围、显示设备 |
| 天窗修作业 | `maintenancewindow` | 天窗计划 | 计划编号、作业日期、作业区间 |
| 继电器检修 | `relay` | 继电器 | 继电器编号、继电器型号、所属设备 |
| 熔断器管理 | `fuse` | 熔断器 | 熔断器编号、额定电流、安装位置 |
| 防雷元件 | `lightning` | 防雷元件 | 元件编号、安装位置、防护等级、泄露电流、动作次数、更换记录 |
| 应急备品 | `emergencyresp` | 应急备品 | 备品编号、备品名称、规格型号 |
| 联锁试验 | `testrecord` | 试验记录 | 试验编号、试验日期、试验车站 |
| 信号故障 | `fault` | 故障记录 | 故障编号、发生时间、故障设备 |
| 检修工具 | `tool` | 检修工具 | 工具编号、工具名称、规格型号 |
| 技术规章 | `regulation` | 技术规章 | 规章编号、规章名称、适用专业 |
| 技能培训 | `training` | 培训记录 | 培训编号、培训主题、培训对象 |

## 约定

- 每个模块的前端页面在 `frontend/src/views/<模块>/index.vue`，后端接口在
  `backend/app/routers/<模块>.py`，业务规则在 `backend/app/services/<模块>.py`。
- 列表接口统一返回 `{ items, total, page, size }`，动作接口统一返回 `{ ok, message }`。
- 状态流转只允许在 `app/services` 里改，路由层不做业务判断；初始化与自检改动不涉及业务规则。
