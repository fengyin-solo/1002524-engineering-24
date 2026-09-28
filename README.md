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
│   ├── dist/                 前端构建产物（npm run build 输出，已 gitignore）
│   ├── package-lock.json     前端依赖锁定，换机直接 npm ci
│   └── vite.config.ts        dev server 配置（open: false）
├── backend/                  FastAPI（Python） 后端
│   ├── app/routers/          每个业务模块一组接口
│   ├── app/services/         业务规则与状态流转
│   ├── app/store.py          内存数据仓库；防雷元件额外落盘到 var/
│   ├── app/bootstrap.py      防雷元件初始化装配与自检（不含业务规则）
│   ├── data/                 初始化数据（入库，本地与线上共用同一份）
│   │   └── lightning_seed.json   防雷元件：覆盖防护有效/泄露超标/动作频繁/已更换
│   ├── var/                  运行期状态（gitignore；lightning.json、日志）
│   ├── logs/backend.log      运行日志（run.sh 自动落盘）
│   ├── tests/                单元测试（python -m unittest）
│   └── requirements.txt      后端依赖锁定到精确版本
├── Makefile
├── .env.example
└── docker-compose.yml
```

## 启动

依赖版本均已锁定（后端 `requirements.txt` 精确到版本号、前端 `package-lock.json`），
换机器安装结果一致。要求 Python 3.11+、Node 20+。

### 一次装好（推荐）

```bash
make install        # 后端自建 .venv 并按锁定版本装依赖；前端 npm ci
```

> 说明：`backend/run.sh` 会自动创建虚拟环境；若已有 `.venv` 指向失效的解释器
> （比如在别的操作系统上创建的目录），会自动删除重建。系统没有 `venv` 模块时
> 自动回退到 `virtualenv`（可先 `pip install --user virtualenv`）。

### 后端

```bash
cd backend
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
./run.sh            # 或 make backend
```

健康检查：`curl http://127.0.0.1:8000/api/health`
运行日志：`backend/logs/backend.log`（终端同时可见，可用 `APP_LOG_PATH` 覆盖位置）

### 前端

```bash
cd frontend
npm ci              # 或 npm install
npm run dev         # 或 make frontend
```

前端默认监听 `http://127.0.0.1:5173/`，dev server 不会自动打开浏览器，
需要自己访问。`/api` 由 vite 代理到后端 `http://127.0.0.1:8000`。

前端构建产物固定输出到 `frontend/dist/`：

```bash
make build          # 等价于 cd frontend && npm run build
```

## 防雷元件：本地开发与数据初始化

防雷元件的初始化数据不再硬编码在代码里，而是仓库内的
**`backend/data/lightning_seed.json`**，本地与线上共用这一份文件。
其中四条记录覆盖：防护有效（正常基线）、**泄露电流超标**、**动作频繁**、**已更换**。

### 约定位置

| 内容 | 位置 | 覆盖方式 |
| --- | --- | --- |
| 初始化数据（入库） | `backend/data/lightning_seed.json` | `LIGHTNING_SEED_PATH` |
| 运行期状态（不入库） | `backend/var/lightning.json` | `LIGHTNING_STATE_PATH` |
| 运行日志 | `backend/logs/backend.log` | `APP_LOG_PATH` |
| 前端构建产物 | `frontend/dist/` | vite `build.outDir` |

### 自检（启动后读防雷元件记录）

```bash
make check          # CLI：cd backend && .venv/bin/python -m app.bootstrap --check
curl http://127.0.0.1:8000/api/lightning/selfcheck
```

自检同时检查依赖与数据，失败时 HTTP 返回 **503**，并用 `reason` 明确归类：

- `dependency_missing`：依赖没装好（提示执行 `pip install -r requirements.txt`）；
- `data_missing`：数据缺失（种子文件缺失/解析失败/记录为空/情形不全）。

返回体里还带 `data.seed_sha256`：换机器部署后两边 hash 相同，即初始化数据一致。

### 初始化与重复初始化

服务启动时会自动执行一次幂等初始化；也可以随时手动触发：

```bash
make init                                              # CLI
curl -X POST http://127.0.0.1:8000/api/lightning/init  # HTTP
```

初始化按业务键（元件编号）合并：**只补缺，不覆盖、不清空**——
已有的测试记录（状态、测试日期、本地新建记录等）原样保留。
运行期的新增与状态流转会写入 `backend/var/lightning.json`，重启不丢。

### 换一台机器重新部署

```bash
make install
make init
make check          # 期望 ok=true，且 seed_sha256 与原机器一致
```

因为种子文件入库、依赖锁定、状态文件按相同规则确定性生成，
全新机器初始化出的防雷元件记录与原机器逐行一致（见 `backend/tests/` 中
`test_fresh_machine_state_is_deterministic`）。测试：`make test`。

Docker 部署同理：种子文件随镜像发布，运行期状态写入挂载卷 `/srv/var`，
容器重启后记录保留（见 `docker-compose.yml`）。


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
| 防雷元件 | `lightning` | 防雷元件 | 元件编号、安装位置、防护等级、泄露电流、动作次数、测试日期、更换记录（示例数据见 `backend/data/lightning_seed.json`） |
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
- 状态流转只允许在 `app/services` 里改，路由层不做业务判断。
