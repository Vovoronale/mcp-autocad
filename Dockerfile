FROM python:3.11-slim

WORKDIR /app

COPY mcp_server/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY mcp_server/ ./

ENV BRIDGE_URL=http://host.docker.internal:8765

CMD ["python", "app.py"]
