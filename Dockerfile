# 中文：Origami API 生产镜像，使用锁定依赖、非 root 用户和独立 artifact 目录。
# English: Origami API production image with locked dependencies, non-root runtime, and a dedicated artifact directory.

ARG PYTHON_IMAGE=python:3.11.13-slim-bookworm
FROM ${PYTHON_IMAGE}

ARG UV_VERSION=0.11.8

ENV PIP_DISABLE_PIP_VERSION_CHECK=1
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONPATH=/app/src
ENV ORIGAMI_ARTIFACT_ROOT=/var/lib/origami/artifacts
ENV UV_CACHE_DIR=/tmp/uv-cache

WORKDIR /app

RUN groupadd --system origami \
    && useradd --system --gid origami --home-dir /home/origami --create-home origami \
    && mkdir -p /var/lib/origami/artifacts \
    && chown -R origami:origami /var/lib/origami /app

COPY pyproject.toml uv.lock ./
RUN python -m pip install --no-cache-dir "uv==${UV_VERSION}" \
    && uv export --locked --no-dev --format requirements-txt --output-file /tmp/requirements.txt \
    && python -m pip install --no-cache-dir -r /tmp/requirements.txt \
    && python -m pip uninstall -y uv \
    && rm -rf /tmp/requirements.txt /tmp/uv-cache

COPY --chown=origami:origami configs ./configs
COPY --chown=origami:origami src ./src

USER origami

EXPOSE 8000
CMD ["python", "-m", "origami.api.app"]
