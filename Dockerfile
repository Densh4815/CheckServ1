FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Создаем пользователя для безопасности
RUN useradd -m -u 1000 botuser && chown -R botuser:botuser /app
USER botuser

# Создаем директории для данных
RUN mkdir -p /app/data /app/logs

EXPOSE 8080

CMD ["python", "maxbot_site_monitor.py"]