FROM python:3.12-slim
WORKDIR /srv/app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
# 初始化数据随镜像发布，与本地共用同一份；运行期状态写到挂载卷 /srv/var
ENV LIGHTNING_SEED_PATH=/srv/app/data/lightning_seed.json \
    LIGHTNING_STATE_PATH=/srv/var/lightning.json \
    APP_LOG_PATH=/srv/var/logs/backend.log
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
