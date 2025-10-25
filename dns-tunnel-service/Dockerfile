FROM python:3.12-slim
WORKDIR /app
COPY . /app

# nevojitet build deps për ndonjë paketë native
RUN apt-get update && apt-get install -y gcc build-essential libpq-dev \
    && rm -rf /var/lib/apt/lists/*

RUN python -m pip install --upgrade pip
RUN pip install --no-cache-dir -r requirements.txt

EXPOSE 8053
CMD ["python", "server.py"]
