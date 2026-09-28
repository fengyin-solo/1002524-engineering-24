FROM python:3.12-slim
WORKDIR /srv/app

# 先装依赖，利用镜像层缓存
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# 初始化数据随镜像一起发布，本地与线上共用同一份 data/seed.json
COPY . .

ENV APP_ENV=production \
    APP_HOST=0.0.0.0 \
    APP_PORT=8000 \
    LOG_DIR=/srv/app/logs

EXPOSE 8000
# 先幂等初始化并自检，通过后再起服务；失败时容器直接退出并打印原因
CMD ["sh", "-c", "python -m app.bootstrap init && exec uvicorn app.main:app --host ${APP_HOST} --port ${APP_PORT}"]
