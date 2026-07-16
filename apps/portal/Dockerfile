FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

RUN useradd --create-home --uid 10002 --shell /usr/sbin/nologin portal
WORKDIR /site
COPY apps/portal/ ./
USER 10002:10002

EXPOSE 8081
CMD ["python", "-m", "http.server", "8081", "--bind", "0.0.0.0", "--directory", "/site"]
