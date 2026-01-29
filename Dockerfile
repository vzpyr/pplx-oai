FROM python:3.11-slim
WORKDIR /app
RUN apt-get update && apt-get install -y git && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*
RUN pip install --no-cache-dir Flask && \
    git clone https://github.com/helallao/perplexity-ai.git && \
    pip install --no-cache-dir -e ./perplexity-ai
COPY app.py .
EXPOSE 5000
CMD ["python", "app.py"]
