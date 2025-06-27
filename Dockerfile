FROM python:3.12-slim

ADD . /app
WORKDIR /app

RUN pip install -r requirements.txt

CMD ["python", "src/sandbox_api_mcp_server/server.py"]