FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir \
    nats-py==2.15.0 \
    "protobuf>=5.27,<7"
COPY agent.py .
COPY pb2/ pb2/
CMD ["python", "-u", "agent.py"]
