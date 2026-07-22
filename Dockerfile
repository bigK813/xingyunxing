FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN mkdir -p /app/data

ENV PORT=8000
ENV DATA_DIR=/app/data

EXPOSE 8000

CMD uvicorn api_server:app --host 0.0.0.0 --port $PORT
