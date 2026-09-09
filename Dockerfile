FROM python:3.12-slim
WORKDIR /app
ENV PYTHONUNBUFFERED=1 TZ=Asia/Seoul
COPY cgv_watch.py config.json ./
CMD ["python", "cgv_watch.py", "--loop", "--interval", "60"]
