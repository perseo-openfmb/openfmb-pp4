FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir \
    flask==3.1.0 \
    pdfplumber==0.11.4 \
    gunicorn==23.0.0

COPY . .

EXPOSE 5500

CMD ["gunicorn", "--bind", "0.0.0.0:5500", "--workers", "2", "app:app"]
