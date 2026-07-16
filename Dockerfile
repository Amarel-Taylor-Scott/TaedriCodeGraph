FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

COPY pyproject.toml README.md ./
COPY src ./src
RUN python -m pip install --no-cache-dir '.[server]' \
    && useradd --create-home --uid 10001 --shell /usr/sbin/nologin taedri \
    && mkdir -p /data /sources \
    && chown -R taedri:taedri /data /sources

USER 10001:10001

EXPOSE 8000
ENTRYPOINT ["tcg"]
CMD ["serve", "--production", "--host", "0.0.0.0", "--port", "8000", "--control", "/data/control.sqlite"]
