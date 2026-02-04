#!/usr/bin/env python3
"""
MaxBot монитор сайта https://home.borodachev-mikhail.ru/
Упрощенная версия без сложных импортов maxbot
"""

import os
import sys
import time
import json
import threading
from datetime import datetime, timedelta
from typing import Dict, Any, List
import urllib.request
import urllib.error
import ssl

# Настройка логирования
import logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('maxbot_monitor.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Конфигурация
CHECK_URL = os.getenv('CHECK_URL', 'https://home.borodachev-mikhail.ru/')
CHECK_INTERVAL = int(os.getenv('CHECK_INTERVAL', '10'))
MAX_CONSECUTIVE_ERRORS = int(os.getenv('MAX_CONSECUTIVE_ERRORS', '3'))

class WebsiteMonitor:
    """Класс для мониторинга сайта"""
    
    def __init__(self, check_url: str, check_interval: int = 10):
        self.check_url = check_url
        self.check_interval = check_interval
        self.ssl_context = ssl._create_unverified_context()
        self.consecutive_errors = 0
        self.site_status = "unknown"
        self.monitoring_active = True
        self.subscribers = []  # Список пользователей
        self.stats = {
            'total_checks': 0,
            'successful_checks': 0,
            'failed_checks': 0,
            'start_time': datetime.now(),
            'last_down_time': None,
            'last_up_time': datetime.now(),
            'uptime_percentage': 100.0
        }
        
    def check_site(self) -> Dict[str, Any]:
        """Проверяет доступность сайта"""
        self.stats['total_checks'] += 1
        check_time = datetime.now()
        
        try:
            headers = {
                'User-Agent': 'MaxBot-Site-Monitor/1.0',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            }
            
            req = urllib.request.Request(self.check_url, headers=headers)
            start_time = time.time()
            
            with urllib.request.urlopen(req, timeout=10, context=self.ssl_context) as response:
                response_time = time.time() - start_time
                status_code = response.getcode()
                
                if 200 <= status_code < 400:
                    self.stats['successful_checks'] += 1
                    self.consecutive_errors = 0
                    
                    if self.site_status != "up":
                        logger.info(f"✅ Сайт восстановлен после {self.consecutive_errors} ошибок")
                    
                    self.site_status = "up"
                    self.stats['last_up_time'] = check_time
                    
                    # Рассчитываем процент аптайма
                    if self.stats['total_checks'] > 0:
                        self.stats['uptime_percentage'] = (
                            self.stats['successful_checks'] / self.stats['total_checks']
                        ) * 100
                    
                    return {
                        'status': 'success',
                        'code': status_code,
                        'response_time': response_time,
                        'message': "✅ Сайт доступен",
                        'details': f"Код: {status_code}, Время ответа: {response_time:.2f}с",
                        'timestamp': check_time
                    }
                else:
                    self.stats['failed_checks'] += 1
                    self.consecutive_errors += 1
                    self.site_status = "down"
                    
                    if not self.stats['last_down_time']:
                        self.stats['last_down_time'] = check_time
                    
                    return {
                        'status': 'error',
                        'code': status_code,
                        'message': f"❌ HTTP ошибка {status_code}",
                        'timestamp': check_time
                    }
                    
        except urllib.error.HTTPError as e:
            self.stats['failed_checks'] += 1
            self.consecutive_errors += 1
            self.site_status = "down"
            
            if not self.stats['last_down_time']:
                self.stats['last_down_time'] = check_time
            
            return {
                'status': 'error',
                'code': e.code,
                'message': f"❌ HTTP ошибка {e.code}: {e.reason}",
                'timestamp': check_time
            }
            
        except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
            self.stats['failed_checks'] += 1
            self.consecutive_errors += 1
            self.site_status = "down"
            
            if not self.stats['last_down_time']:
                self.stats['last_down_time'] = check_time
            
            error_msg = str(e.reason) if hasattr(e, 'reason') else str(e)
            return {
                'status': 'error',
                'message': f"❌ Ошибка подключения: {error_msg}",
                'timestamp': check_time
            }
            
        except Exception as e:
            self.stats['failed_checks'] += 1
            self.consecutive_errors += 1
            self.site_status = "down"
            
            if not self.stats['last_down_time']:
                self.stats['last_down_time'] = check_time
            
            return {
                'status': 'error',
                'message': f"❌ Неизвестная ошибка: {str(e)}",
                'timestamp': check_time
            }
    
    def get_stats(self) -> Dict[str, Any]:
        """Получает статистику мониторинга"""
        uptime = datetime.now() - self.stats['start_time']
        
        return {
            'site_url': self.check_url,
            'current_status': "🟢 Доступен" if self.site_status == "up" else "🔴 Недоступен",
            'uptime': str(uptime).split('.')[0],
            'total_checks': self.stats['total_checks'],
            'successful_checks': self.stats['successful_checks'],
            'failed_checks': self.stats['failed_checks'],
            'uptime_percentage': f"{self.stats['uptime_percentage']:.2f}%",
            'consecutive_errors': self.consecutive_errors,
            'last_down_time': self.stats['last_down_time'].strftime("%Y-%m-%d %H:%M:%S") 
                if self.stats['last_down_time'] else "Нет",
            'last_up_time': self.stats['last_up_time'].strftime("%Y-%m-%d %H:%M:%S"),
            'subscribers_count': len(self.subscribers)
        }
    
    def add_subscriber(self, user_id: str):
        """Добавляет подписчика на уведомления"""
        if user_id not in self.subscribers:
            self.subscribers.append(user_id)
            logger.info(f"Добавлен подписчик: {user_id}")
            return True
        return False
    
    def remove_subscriber(self, user_id: str):
        """Удаляет подписчика"""
        if user_id in self.subscribers:
            self.subscribers.remove(user_id)
            logger.info(f"Удален подписчик: {user_id}")
            return True
        return False
    
    def is_subscriber(self, user_id: str) -> bool:
        """Проверяет, является ли пользователь подписчиком"""
        return user_id in self.subscribers
    
    def start_monitoring(self):
        """Запускает мониторинг в отдельном потоке"""
        def monitor_loop():
            logger.info(f"🚀 Запуск мониторинга сайта: {self.check_url}")
            logger.info(f"⏱️ Интервал проверки: {self.check_interval} секунд")
            
            while self.monitoring_active:
                try:
                    result = self.check_site()
                    
                    # Логируем результат
                    if result['status'] == 'success':
                        logger.info(f"Проверка #{self.stats['total_checks']}: {result['message']}")
                    else:
                        logger.error(f"Проверка #{self.stats['total_checks']}: {result['message']}")
                        
                        # Если это критическая ошибка
                        if self.consecutive_errors >= MAX_CONSECUTIVE_ERRORS:
                            logger.error(f"🚨 КРИТИЧЕСКАЯ ОШИБКА! {self.consecutive_errors} ошибок подряд!")
                    
                    time.sleep(self.check_interval)
                    
                except Exception as e:
                    logger.error(f"Ошибка в цикле мониторинга: {e}")
                    time.sleep(self.check_interval)
        
        # Запускаем мониторинг в отдельном потоке
        monitor_thread = threading.Thread(target=monitor_loop, daemon=True)
        monitor_thread.start()
        return monitor_thread
    
    def stop_monitoring(self):
        """Останавливает мониторинг"""
        self.monitoring_active = False
        logger.info("🛑 Мониторинг остановлен")

class SimpleBot:
    """Простой бот для обработки команд"""
    
    def __init__(self, monitor: WebsiteMonitor):
        self.monitor = monitor
        self.commands = {
            '/start': self.handle_start,
            '/status': self.handle_status,
            '/stats': self.handle_stats,
            '/subscribe': self.handle_subscribe,
            '/unsubscribe': self.handle_unsubscribe,
            '/help': self.handle_help,
        }
    
    def handle_command(self, command: str, user_id: str = "user123") -> str:
        """Обрабатывает команду"""
        command = command.strip().lower()
        
        # Проверяем известные команды
        for cmd, handler in self.commands.items():
            if command == cmd.lower():
                return handler(user_id)
        
        # Проверяем приветствия
        if command in ['привет', 'hello', 'hi', 'здравствуй']:
            return self.handle_greeting(user_id)
        
        # Проверяем прощания
        if command in ['пока', 'до свидания', 'bye', 'goodbye']:
            return self.handle_goodbye()
        
        # Если команда не распознана
        return self.handle_unknown()
    
    def handle_start(self, user_id: str) -> str:
        """Обработка команды /start"""
        return f"""🚀 **Мониторинг сайта активирован!**

Я отслеживаю доступность сайта:
🌐 {self.monitor.check_url}

**Доступные команды:**
/status - Текущий статус сайта
/stats - Подробная статистика
/subscribe - Подписаться на уведомления
/unsubscribe - Отписаться от уведомлений
/help - Справка по командам

⚡ **Примечание:** Автоматическая проверка каждые {self.monitor.check_interval} секунд"""
    
    def handle_status(self, user_id: str) -> str:
        """Обработка команды /status"""
        stats = self.monitor.get_stats()
        
        # Определяем текущий статус
        if self.monitor.site_status == "up":
            status_message = "✅ Сайт работает стабильно"
        else:
            if self.monitor.consecutive_errors >= MAX_CONSECUTIVE_ERRORS:
                status_message = "🚨 КРИТИЧЕСКАЯ ОШИБКА! Требуется вмешательство!"
            else:
                status_message = "⚠️ Проблемы с доступностью сайта"
        
        return f"""📊 **Текущий статус сайта:**

🌐 Сайт: {stats['site_url']}
🔄 Статус: {stats['current_status']}
⏱️ Последняя проверка: {datetime.now().strftime("%H:%M:%S")}
🔴 Ошибок подряд: {stats['consecutive_errors']}

{status_message}"""
    
    def handle_stats(self, user_id: str) -> str:
        """Обработка команды /stats"""
        stats = self.monitor.get_stats()
        
        return f"""📈 **Статистика мониторинга:**

🌐 Сайт: {stats['site_url']}
⏱️ Аптайм: {stats['uptime']}
🔄 Всего проверок: {stats['total_checks']}
✅ Успешно: {stats['successful_checks']}
❌ Ошибок: {stats['failed_checks']}
📊 Доступность: {stats['uptime_percentage']}
👥 Подписчиков: {stats['subscribers_count']}

⏰ Последний сбой: {stats['last_down_time']}
🕒 Работает с: {self.monitor.stats['start_time'].strftime("%Y-%m-%d %H:%M:%S")}"""
    
    def handle_subscribe(self, user_id: str) -> str:
        """Обработка команды /subscribe"""
        if self.monitor.is_subscriber(user_id):
            return "❌ Вы уже подписаны на уведомления!"
        
        self.monitor.add_subscriber(user_id)
        return "✅ Вы успешно подписались на уведомления!\n\nВы будете получать сообщения при проблемах с сайтом."
    
    def handle_unsubscribe(self, user_id: str) -> str:
        """Обработка команды /unsubscribe"""
        if not self.monitor.is_subscriber(user_id):
            return "❌ Вы не подписаны на уведомления!"
        
        self.monitor.remove_subscriber(user_id)
        return "✅ Вы отписались от уведомлений.\n\nБольше не будете получать сообщения о проблемах с сайтом."
    
    def handle_help(self, user_id: str) -> str:
        """Обработка команды /help"""
        return f"""ℹ️ **Справка по командам:**

**Основные команды:**
/start - Начало работы с ботом
/status - Текущий статус сайта
/stats - Подробная статистика мониторинга
/subscribe - Подписаться на уведомления
/unsubscribe - Отписаться от уведомлений
/help - Эта справка

**Информация о мониторинге:**
• Сайт проверяется каждые {self.monitor.check_interval} секунд
• Уведомления отправляются при сбоях
• Статистика обновляется в реальном времени
• Бот работает 24/7

🌐 **Мониторим:** {self.monitor.check_url}"""
    
    def handle_greeting(self, user_id: str) -> str:
        """Обработка приветствия"""
        return f"""👋 Привет! Я бот для мониторинга сайтов.

Я отслеживаю доступность сайта {self.monitor.check_url}.

Напишите /help для списка команд или /status для проверки текущего состояния."""
    
    def handle_goodbye(self) -> str:
        """Обработка прощания"""
        return "👋 До свидания! Надеюсь, сайт будет стабильным!\n\nНе забывайте проверять статус командой /status"
    
    def handle_unknown(self) -> str:
        """Обработка неизвестной команды"""
        return """🤔 Я не понял ваше сообщение.

Попробуйте одну из команд:
• /start - Начало работы
• /status - Статус сайта
• /stats - Статистика
• /help - Справка"""

def run_interactive_mode():
    """Запускает интерактивный режим для тестирования"""
    print("=" * 60)
    print("🤖 ПРОСТОЙ МОНИТОР САЙТА")
    print("=" * 60)
    print(f"🌐 Мониторинг сайта: {CHECK_URL}")
    print(f"⏱️ Интервал проверки: {CHECK_INTERVAL} сек")
    print("=" * 60)
    print("\nДоступные команды:")
    print("  /start     - Начало работы")
    print("  /status    - Статус сайта")
    print("  /stats     - Статистика")
    print("  /subscribe - Подписаться")
    print("  /unsubscribe - Отписаться")
    print("  /help      - Справка")
    print("  привет     - Приветствие")
    print("  пока       - Прощание")
    print("  exit       - Выход")
    print("=" * 60)
    
    # Инициализация монитора и бота
    monitor = WebsiteMonitor(CHECK_URL, CHECK_INTERVAL)
    bot = SimpleBot(monitor)
    
    # Запуск мониторинга
    monitor.start_monitoring()
    
    user_id = "user123"
    
    try:
        while True:
            user_input = input("\nВы: ").strip()
            
            if user_input.lower() == 'exit':
                print("\n👋 До свидания!")
                monitor.stop_monitoring()
                break
            
            # Обрабатываем команду
            response = bot.handle_command(user_input, user_id)
            print(f"\nБот: {response}")
            
    except KeyboardInterrupt:
        print("\n\n🛑 Остановка бота...")
        monitor.stop_monitoring()

def run_webhook_mode():
    """Запускает режим для вебхука (простой HTTP сервер)"""
    from http.server import HTTPServer, BaseHTTPRequestHandler
    import json
    
    class BotHandler(BaseHTTPRequestHandler):
        def __init__(self, *args, **kwargs):
            self.monitor = WebsiteMonitor(CHECK_URL, CHECK_INTERVAL)
            self.bot = SimpleBot(self.monitor)
            self.monitor.start_monitoring()
            super().__init__(*args, **kwargs)
        
        def do_GET(self):
            """Обработка GET запросов"""
            if self.path == '/health':
                self.send_response(200)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                response = {
                    'status': 'ok',
                    'service': 'site-monitor-bot',
                    'timestamp': datetime.now().isoformat()
                }
                self.wfile.write(json.dumps(response).encode())
            
            elif self.path == '/status':
                self.send_response(200)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                response = self.monitor.get_stats()
                self.wfile.write(json.dumps(response).encode())
            
            else:
                self.send_response(404)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                response = {'error': 'Not found'}
                self.wfile.write(json.dumps(response).encode())
        
        def do_POST(self):
            """Обработка POST запросов (имитация вебхука)"""
            content_length = int(self.headers['Content-Length'])
            post_data = self.rfile.read(content_length)
            
            try:
                data = json.loads(post_data.decode('utf-8'))
                user_id = data.get('user_id', 'unknown')
                message = data.get('message', '')
                
                # Обрабатываем команду
                response_text = self.bot.handle_command(message, user_id)
                
                # Отправляем ответ
                self.send_response(200)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                response = {
                    'response': response_text,
                    'user_id': user_id,
                    'timestamp': datetime.now().isoformat()
                }
                self.wfile.write(json.dumps(response).encode())
                
            except Exception as e:
                self.send_response(500)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                response = {'error': str(e)}
                self.wfile.write(json.dumps(response).encode())
        
        def log_message(self, format, *args):
            """Переопределяем логирование"""
            logger.info("%s - - [%s] %s" % (self.address_string(),
                                            self.log_date_time_string(),
                                            format % args))
    
    # Запускаем HTTP сервер
    host = '0.0.0.0'
    port = 8080
    
    logger.info(f"🚀 Запуск веб-сервера на {host}:{port}")
    logger.info(f"🌐 Мониторинг: {CHECK_URL}")
    logger.info(f"⏱️ Интервал: {CHECK_INTERVAL} сек")
    logger.info("\nДоступные эндпоинты:")
    logger.info("  GET /health  - Проверка здоровья")
    logger.info("  GET /status  - Статус мониторинга")
    logger.info("  POST /       - Вебхук для команд бота")
    
    server = HTTPServer((host, port), BotHandler)
    
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        logger.info("\n🛑 Остановка сервера...")
        server.server_close()

def main():
    """Основная функция запуска"""
    print("🚀 Запуск монитора сайта...")
    print("=" * 60)
    
    if len(sys.argv) > 1:
        if sys.argv[1] == "--interactive":
            run_interactive_mode()
        elif sys.argv[1] == "--webhook":
            run_webhook_mode()
        else:
            print("Неизвестный аргумент. Используйте:")
            print("  --interactive  - Интерактивный режим")
            print("  --webhook      - Вебхук режим")
            sys.exit(1)
    else:
        # Режим по умолчанию - демонстрация
        print("✅ Монитор сайта запущен!")
        print(f"🌐 Мониторинг: {CHECK_URL}")
        print(f"⏱️ Интервал: {CHECK_INTERVAL} секунд")
        print("\nРежимы работы:")
        print("  --interactive  - Интерактивный режим для тестирования")
        print("  --webhook      - Вебхук режим (HTTP сервер)")
        print("\nПример использования:")
        print("  python maxbot_site_monitor.py --interactive")
        print("  python maxbot_site_monitor.py --webhook")
        print("=" * 60)
        
        # Просто запускаем мониторинг в фоне
        monitor = WebsiteMonitor(CHECK_URL, CHECK_INTERVAL)
        monitor.start_monitoring()
        
        try:
            while True:
                time.sleep(60)
        except KeyboardInterrupt:
            print("\n👋 Остановка монитора...")
            monitor.stop_monitoring()

if __name__ == "__main__":
    main()
