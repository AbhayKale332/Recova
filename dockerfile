FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
	PYTHONUNBUFFERED=1 \
	PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY Backend/dependencies.txt ./dependencies.txt

RUN pip install --upgrade pip \
	&& pip install -r dependencies.txt \
	&& pip install "mcp>=1.12.0,<2.0.0" "openai>=3.8.0" \
	&& useradd --create-home --uid 10001 appuser

COPY Backend/application ./application
COPY Backend/main.py ./main.py
COPY Backend/pyproject.toml ./pyproject.toml

RUN chown -R appuser:appuser /app
USER appuser

EXPOSE 8000

CMD ["sh", "-c", "uvicorn application.server:app --host 0.0.0.0 --port ${PORT:-8000}"]
