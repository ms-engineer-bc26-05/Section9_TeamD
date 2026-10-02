FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000

# 起動の設定（自動リロード・ワーカー数・アクセスログ）は app/run.py にまとめている
CMD ["python", "-m", "app.run"]