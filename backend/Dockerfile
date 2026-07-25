FROM python:3.12-slim

WORKDIR /app

RUN pip install uv --quiet

COPY pyproject.toml requirements.txt ./
RUN uv pip install --system -r requirements.txt --quiet

COPY . .

EXPOSE 8080

ENV PYTHONPATH=/app

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080"]
