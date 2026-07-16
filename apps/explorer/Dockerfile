FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

RUN useradd --create-home --uid 10001 --shell /usr/sbin/nologin explorer
WORKDIR /site
COPY apps/explorer/ ./
USER 10001:10001

EXPOSE 8080
CMD ["python", "-m", "http.server", "8080", "--bind", "0.0.0.0", "--directory", "/site"]
