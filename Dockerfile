FROM python:3.11-slim

WORKDIR /app

# Устанавливаем системные зависимости
RUN apt-get update && apt-get install -y \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Копируем requirements и устанавливаем зависимости
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Копируем исходный код
COPY . .

# Создаем пользователя для безопасности
RUN useradd -m -u 1000 botuser && chown -R botuser:botuser /app
USER botuser

# Создаем директории для данных
RUN mkdir -p /app/data /app/logs

# Открываем порт для вебхука
EXPOSE 8080

# Команда запуска (по умолчанию вебхук режим)
CMD ["python", "maxbot_site_monitor.py", "--webhook"]
