FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app.py .

# Create /data directory for persistent volume mount
# This will be used if Railway volume is mounted at /data
RUN mkdir -p /data

CMD ["python", "app.py"]
