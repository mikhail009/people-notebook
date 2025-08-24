# -------- Build runtime --------
FROM python:3.12-slim


ENV PYTHONDONTWRITEBYTECODE=1 \
PYTHONUNBUFFERED=1


# System deps
RUN apt-get update && apt-get install -y --no-install-recommends \
build-essential \
&& rm -rf /var/lib/apt/lists/*


WORKDIR /app


# Copy deps first for better caching
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt


# Copy app
COPY app ./app


# Create data dir for SQLite
RUN mkdir -p /data
VOLUME ["/data"]


# Default envs
ENV DB_PATH=/data/app.db \
ADMIN_USER=admin \
ADMIN_PASS=changeme


EXPOSE 8000


CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
