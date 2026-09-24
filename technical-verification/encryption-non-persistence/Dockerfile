FROM python:3.12-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app.py test_encryption.py ./

CMD ["python", "-m", "pytest", "-q", "-p", "no:cacheprovider", "-o", "asyncio_default_fixture_loop_scope=function"]