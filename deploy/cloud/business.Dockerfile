# syntax=docker/dockerfile:1
FROM node:24-bookworm-slim AS diagrams
WORKDIR /runtime
RUN corepack enable && corepack prepare pnpm@11.10.0 --activate
COPY services/business/backend/portal/product_assets/mermaid-runtime/ ./
RUN pnpm install --frozen-lockfile && pnpm build

WORKDIR /harness
COPY services/business/harness/package.json services/business/harness/package-lock.json ./
RUN npm ci --omit=dev --ignore-scripts --registry=https://registry.npmjs.org
COPY services/business/harness/runner.mjs ./

FROM ghcr.io/astral-sh/uv:0.11.17@sha256:03bdc89bb9798628846e60c3a9ad19006c8c3c724ccd2985a33145c039a0577b AS uv

FROM python:3.13-slim-bookworm
RUN apt-get update && apt-get install -y --no-install-recommends \
    libreoffice-writer libreoffice-impress python3-uno chromium fonts-noto-cjk \
    fonts-crosextra-carlito fonts-crosextra-caladea fontconfig poppler-utils libgl1 libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*
COPY --from=diagrams /usr/local/bin/node /usr/local/bin/node
COPY deploy/cloud/requirements.lock /tmp/requirements.lock
RUN pip install --no-cache-dir -r /tmp/requirements.lock
# RapidOCR 1.4.4 supports Python <3.13; keep it outside the business interpreter.
COPY --from=uv /uv /uvx /bin/
COPY services/business/backend/portal/source_parsers/requirements.txt /tmp/intake-requirements.txt
ENV UV_PYTHON_INSTALL_DIR=/opt/uv-python \
    PORTAL_PRODUCT_PARSER_PYTHON=/opt/product-parser/bin/python
RUN uv python install 3.12 \
    && uv venv --python 3.12 /opt/product-parser \
    && uv pip sync --python /opt/product-parser/bin/python /tmp/intake-requirements.txt \
    && uv pip check --python /opt/product-parser/bin/python \
    && rm -rf /root/.cache/uv
WORKDIR /app/services/business
COPY services/business/backend/ ./backend/
COPY services/business/model_gateway/ ./model_gateway/
COPY --from=diagrams /harness/ ./harness/
COPY --from=diagrams /runtime/ ./backend/portal/product_assets/mermaid-runtime/
COPY services/engineering/ /app/services/engineering/
COPY deploy/cloud/fonts.conf /etc/fonts/conf.d/99-enterprise-fonts.conf
COPY deploy/cloud/entrypoint.py /app/cloud_entrypoint.py
COPY deploy/cloud/image_checks.py deploy/cloud/render_smoke.py /app/cloud/
RUN groupadd --gid 10001 portal && useradd --uid 10001 --gid portal --create-home portal \
    && mkdir -p /data/product /data/hr /data/tender /data/engineering /data/imports staticfiles \
    && chown -R portal:portal /data staticfiles && fc-cache -f
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=/app/services/business/backend:/app/services/business
USER portal
ENTRYPOINT ["python", "/app/cloud_entrypoint.py"]
CMD ["portal"]
