FROM python:3.13-slim-bookworm
WORKDIR /app
COPY deploy/cloud/requirements.lock /tmp/requirements.lock
RUN pip install --no-cache-dir -r /tmp/requirements.lock
COPY platform/app/ ./app/
COPY platform/alembic/ ./alembic/
COPY platform/alembic.ini ./
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080", "--no-access-log"]
