# 中文：Origami API 本地开发镜像，把运行依赖预先安装进镜像，避免 compose up 时重复下载。
# English: Local Origami API image with runtime dependencies preinstalled for fast compose startup.

FROM python:3.11-slim

ENV PIP_DISABLE_PIP_VERSION_CHECK=1
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/workspace/src

WORKDIR /workspace

COPY pyproject.toml ./
RUN ["python", "-c", "import subprocess, sys, tomllib; deps = tomllib.load(open('pyproject.toml', 'rb'))['project']['dependencies']; subprocess.check_call([sys.executable, '-m', 'pip', 'install', '--no-cache-dir', *deps])"]

COPY src ./src

CMD ["python", "-m", "origami.api.app"]
