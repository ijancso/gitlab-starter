FROM python:3.12-slim

WORKDIR /app

# Copy project metadata first so pip layer is cached until deps change.
COPY pyproject.toml ./
COPY src/ ./src/

RUN pip install --no-cache-dir ".[geo]"

EXPOSE 8000

CMD ["uvicorn", "geo.api:app", "--host", "0.0.0.0", "--port", "8000"]
