#!/usr/bin/env python3
"""
MaxBot монитор сайта https://home.borodachev-mikhail.ru/
Интеграция с платформой Bothost для профессионального хостинга
"""

import os
import sys
import time
import asyncio
import logging
import json
import urllib.request
import urllib.error
import ssl
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
from maxbot import MaxBot, Message, User, Chat
from maxbot.handlers import CommandHandler, MessageHandler, CallbackHandler
from maxbot.keyboards import InlineKeyboard, ReplyKeyboard
from maxbot.filters import Filter
import threading

# Настройка логирования
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
CHECK_URL = "https://home.borodachev-mikhail.ru/"
CHECK_INTERVAL = 10  # секунд
MAX_CONSECUTIVE_ERRORS = 3

class WebsiteMonitor:
    """Класс для мониторинга сайта"""
    
    def __init__(self, check_url: str, check_interval: int = 10):
        self.check_url = check_url
        self.check_interval = check_interval
        self.ssl_context = ssl._create_unverified_context()
        self.consecutive_errors = 0
        self.site_status = "unknown"
        self.monitoring_active = True
        self.subscribers = []  # Список chat_id подписчиков
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
                'Accept-Language': 'ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7',
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
                        'message': f"✅ Сайт доступен",
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
    
    def add_subscriber(self, chat_id: str):
        """Добавляет подписчика на уведомления"""
        if chat_id not in self.subscribers:
            self.subscribers.append(chat_id)
            logger.info(f"Добавлен подписчик: {chat_id}")
    
    def remove_subscriber(self, chat_id: str):
        """Удаляет подписчика"""
        if chat_id in self.subscribers:
            self.subscribers.remove(chat_id)
            logger.info(f"Удален подписчик: {chat_id}")
    
    def is_subscriber(self, chat_id: str) -> bool:
        """Проверяет, является ли пользователь подписчиком"""
        return chat_id in self.subscribers
    
    def start_monitoring(self, callback_func=None):
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
                        
                        # Если это критическая ошибка и есть подписчики
                        if self.consecutive_errors >= MAX_CONSECUTIVE_ERRORS:
                            if callback_func and self.subscribers:
                                for subscriber in self.subscribers:
                                    callback_func(subscriber, result)
                    
                    # Если сайт восстановился после ошибок
                    if result['status'] == 'success' and self.consecutive_errors == 1:
                        if callback_func and self.subscribers:
                            for subscriber in self.subscribers:
                                callback_func(subscriber, result, recovery=True)
                    
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

class MaxBotSiteMonitor:
    """Основной класс MaxBot для мониторинга сайта"""
    
    def __init__(self):
        # Инициализация монитора сайта
        self.monitor = WebsiteMonitor(CHECK_URL, CHECK_INTERVAL)
        
        # Создаем экземпляр MaxBot с инлайн YAML конфигурацией
        self.bot = MaxBot.inline("""
            dialog:
              # Команда /start
              - condition: message.text == '/start'
                response: |
                  🚀 **Мониторинг сайта активирован!**
                  
                  Я буду отслеживать доступность сайта:
                  🌐 {{ site_url }}
                  
                  **Доступные команды:**
                  /status - Текущий статус сайта
                  /stats - Подробная статистика
                  /subscribe - Подписаться на уведомления
                  /unsubscribe - Отписаться от уведомлений
                  /help - Справка по командам
                  
                  ⚡ **Примечание:** Бот автоматически проверяет сайт каждые 10 секунд
                
                bindings:
                  site_url: "{{ monitor.check_url }}"
              
              # Команда /status
              - condition: message.text == '/status'
                response: |
                  📊 **Текущий статус сайта:**
                  
                  🌐 Сайт: {{ site_url }}
                  🔄 Статус: {{ status }}
                  ⏱️ Последняя проверка: {{ last_check }}
                  🔴 Ошибок подряд: {{ errors }}
                  
                  {{ status_details }}
                
                bindings:
                  site_url: "{{ monitor.check_url }}"
                  status: "{{ current_status }}"
                  last_check: "{{ last_check_time }}"
                  errors: "{{ consecutive_errors }}"
                  status_details: "{{ status_message }}"
              
              # Команда /stats
              - condition: message.text == '/stats'
                response: |
                  📈 **Статистика мониторинга:**
                  
                  🌐 Сайт: {{ site_url }}
                  ⏱️ Аптайм: {{ uptime }}
                  🔄 Всего проверок: {{ total_checks }}
                  ✅ Успешно: {{ successful }}
                  ❌ Ошибок: {{ failed }}
                  📊 Доступность: {{ availability }}
                  👥 Подписчиков: {{ subscribers }}
                  
                  ⏰ Последний сбой: {{ last_down }}
                  🕒 Работает с: {{ start_time }}
                
                bindings:
                  site_url: "{{ site_url }}"
                  uptime: "{{ uptime }}"
                  total_checks: "{{ total_checks }}"
                  successful: "{{ successful_checks }}"
                  failed: "{{ failed_checks }}"
                  availability: "{{ uptime_percentage }}"
                  subscribers: "{{ subscribers_count }}"
                  last_down: "{{ last_down_time }}"
                  start_time: "{{ start_time }}"
              
              # Команда /subscribe
              - condition: message.text == '/subscribe'
                response: |
                  {{ subscribe_result }}
                
                bindings:
                  subscribe_result: "{{ subscription_message }}"
              
              # Команда /unsubscribe
              - condition: message.text == '/unsubscribe'
                response: |
                  {{ unsubscribe_result }}
                
                bindings:
                  unsubscribe_result: "{{ unsubscription_message }}"
              
              # Команда /help
              - condition: message.text == '/help'
                response: |
                  ℹ️ **Справка по командам:**
                  
                  **Основные команды:**
                  /start - Начало работы с ботом
                  /status - Текущий статус сайта
                  /stats - Подробная статистика мониторинга
                  /subscribe - Подписаться на уведомления
                  /unsubscribe - Отписаться от уведомлений
                  /help - Эта справка
                  
                  **Информация о мониторинге:**
                  • Сайт проверяется каждые 10 секунд
                  • Уведомления отправляются при сбоях
                  • Статистика обновляется в реальном времени
                  • Бот работает 24/7
                  
                  🌐 **Мониторим:** {{ site_url }}
                
                bindings:
                  site_url: "{{ monitor.check_url }}"
              
              # Приветственные сообщения
              - condition: message.text.lower() in ['привет', 'hello', 'hi', 'здравствуй']
                response: |
                  👋 Привет! Я бот для мониторинга сайтов.
                  
                  Я отслеживаю доступность сайта {{ site_url }}.
                  
                  Напишите /help для списка команд или /status для проверки текущего состояния.
                
                bindings:
                  site_url: "{{ monitor.check_url }}"
              
              # Прощание
              - condition: message.text.lower() in ['пока', 'до свидания', 'bye', 'goodbye']
                response: |
                  👋 До свидания! Надеюсь, сайт будет стабильным!
                  
                  Не забывайте проверять статус командой /status
              
              # Ответ по умолчанию
              - condition: true
                response: |
                  🤔 Я не понял ваше сообщение.
                  
                  Попробуйте одну из команд:
                  • /start - Начало работы
                  • /status - Статус сайта
                  • /stats - Статистика
                  • /help - Справка
        """)
        
        # Настраиваем переменные для шаблонов
        self.setup_bindings()
        
        # Запускаем мониторинг
        self.monitor.start_monitoring(self.send_notification)
    
    def setup_bindings(self):
        """Настраивает переменные для шаблонов MaxBot"""
        # Обновляем контекст бота с нашими данными
        self.bot.context.update({
            'monitor': self.monitor,
            'get_stats': self.get_stats_for_template,
            'subscribe_user': self.subscribe_user,
            'unsubscribe_user': self.unsubscribe_user
        })
    
    def get_stats_for_template(self) -> Dict[str, Any]:
        """Получает статистику для шаблона"""
        stats = self.monitor.get_stats()
        
        # Определяем текущий статус
        if self.monitor.site_status == "up":
            current_status = "🟢 Доступен"
            status_message = "✅ Сайт работает стабильно"
        else:
            current_status = "🔴 Недоступен"
            if self.monitor.consecutive_errors >= MAX_CONSECUTIVE_ERRORS:
                status_message = "🚨 КРИТИЧЕСКАЯ ОШИБКА! Требуется вмешательство!"
            else:
                status_message = "⚠️ Проблемы с доступностью сайта"
        
        return {
            'site_url': stats['site_url'],
            'current_status': current_status,
            'last_check_time': datetime.now().strftime("%H:%M:%S"),
            'consecutive_errors': stats['consecutive_errors'],
            'status_message': status_message,
            'uptime': stats['uptime'],
            'total_checks': stats['total_checks'],
            'successful_checks': stats['successful_checks'],
            'failed_checks': stats['failed_checks'],
            'uptime_percentage': stats['uptime_percentage'],
            'subscribers_count': stats['subscribers_count'],
            'last_down_time': stats['last_down_time'],
            'start_time': self.monitor.stats['start_time'].strftime("%Y-%m-%d %H:%M:%S")
        }
    
    def subscribe_user(self, chat_id: str) -> str:
        """Подписывает пользователя на уведомления"""
        if self.monitor.is_subscriber(chat_id):
            return "❌ Вы уже подписаны на уведомления!"
        
        self.monitor.add_subscriber(chat_id)
        return "✅ Вы успешно подписались на уведомления!\n\nВы будете получать сообщения при проблемах с сайтом."
    
    def unsubscribe_user(self, chat_id: str) -> str:
        """Отписывает пользователя от уведомлений"""
        if not self.monitor.is_subscriber(chat_id):
            return "❌ Вы не подписаны на уведомления!"
        
        self.monitor.remove_subscriber(chat_id)
        return "✅ Вы отписались от уведомлений.\n\nБольше не будете получать сообщения о проблемах с сайтом."
    
    def send_notification(self, chat_id: str, result: Dict[str, Any], recovery: bool = False):
        """Отправляет уведомление пользователю"""
        try:
            if recovery:
                message = self.format_recovery_message(result)
            else:
                message = self.format_error_message(result)
            
            # Здесь должна быть реальная отправка через Max API
            # В демо-режиме просто логируем
            logger.info(f"📨 Уведомление для {chat_id}: {message[:50]}...")
            
        except Exception as e:
            logger.error(f"Ошибка отправки уведомления: {e}")
    
    def format_error_message(self, result: Dict[str, Any]) -> str:
        """Форматирует сообщение об ошибке"""
        timestamp = result['timestamp'].strftime("%Y-%m-%d %H:%M:%S")
        
        if self.monitor.consecutive_errors == 1:
            return f"""🚨 **ОБНАРУЖЕНА ПРОБЛЕМА!**

🌐 Сайт: {self.monitor.check_url}
🕒 Время: {timestamp}
❌ Ошибка: {result['message']}
🔢 Ошибок подряд: {self.monitor.consecutive_errors}

⚠️ Начато наблюдение за ситуацией"""
        
        elif self.monitor.consecutive_errors >= MAX_CONSECUTIVE_ERRORS:
            return f"""🚨🚨🚨 **КРИТИЧЕСКАЯ ОШИБКА!**

🌐 Сайт: {self.monitor.check_url}
🕒 Время: {timestamp}
🔴 Ошибок подряд: {self.monitor.consecutive_errors}
❌ Последняя ошибка: {result['message']}

🚨 ТРЕБУЕТСЯ СРОЧНОЕ ВМЕШАТЕЛЬСТВО!"""
        
        else:
            return f"""🔴 **Сайт всё ещё недоступен**

🌐 {self.monitor.check_url}
🕒 {timestamp}
🔢 Ошибок подряд: {self.monitor.consecutive_errors}
❌ {result['message']}"""
    
    def format_recovery_message(self, result: Dict[str, Any]) -> str:
        """Форматирует сообщение о восстановлении"""
        timestamp = result['timestamp'].strftime("%Y-%m-%d %H:%M:%S")
        
        downtime = "неизвестно"
        if self.monitor.stats['last_down_time']:
            downtime_duration = result['timestamp'] - self.monitor.stats['last_down_time']
            downtime = str(downtime_duration).split('.')[0]
        
        return f"""✅ **САЙТ ВОССТАНОВЛЕН!**

🌐 Сайт: {self.monitor.check_url}
🕒 Время восстановления: {timestamp}
⏱️ Простой: {downtime}
⚡ Время ответа: {result.get('response_time', 0):.2f}с
📊 Код ответа: {result.get('code', 'N/A')}

🎉 Сайт снова доступен для пользователей"""
    
    def process_message(self, message_text: str, chat_id: str = "user123") -> str:
        """Обрабатывает входящее сообщение (для демо-режима)"""
        try:
            # Создаем объект сообщения
            message = type('Message', (), {
                'text': message_text,
                'from_user': type('User', (), {
                    'id': chat_id,
                    'username': 'demo_user'
                })()
            })()
            
            # Получаем ответ от бота
            response = self.bot.process_message(message)
            
            # Извлекаем текст из ответа
            if hasattr(response, 'render'):
                return response.render()
            elif hasattr(response, 'value'):
                return str(response.value)
            else:
                return str(response)
                
        except Exception as e:
            logger.error(f"Ошибка обработки сообщения: {e}")
            return "⚠️ Произошла ошибка при обработке сообщения."
    
    def run_interactive(self):
        """Запускает интерактивный режим для тестирования"""
        print("=" * 60)
        print("🤖 MAXBOT МОНИТОР САЙТА")
        print("=" * 60)
        print(f"🌐 Мониторинг сайта: {self.monitor.check_url}")
        print(f"⏱️ Интервал проверки: {self.monitor.check_interval} сек")
        print(f"👤 ID чата: user123 (демо-режим)")
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
        
        chat_id = "user123"
        
        while True:
            try:
                user_input = input("\nВы: ").strip()
                
                if user_input.lower() == 'exit':
                    print("\n👋 До свидания!")
                    self.monitor.stop_monitoring()
                    break
                
                # Обрабатываем сообщение
                response = self.process_message(user_input, chat_id)
                print(f"\nБот: {response}")
                
            except KeyboardInterrupt:
                print("\n\n🛑 Остановка бота...")
                self.monitor.stop_monitoring()
                break
            except Exception as e:
                print(f"\n⚠️ Ошибка: {e}")

def main():
    """Основная функция запуска"""
    print("🚀 Запуск MaxBot монитора сайта...")
    print("=" * 60)
    
    # Инициализация бота
    bot_monitor = MaxBotSiteMonitor()
    
    # Проверяем аргументы командной строки
    if len(sys.argv) > 1 and sys.argv[1] == "--interactive":
        # Интерактивный режим для тестирования
        bot_monitor.run_interactive()
    else:
        # Режим демонстрации (без интерактивного ввода)
        print("✅ MaxBot монитор сайта запущен!")
        print(f"🌐 Мониторинг: {CHECK_URL}")
        print(f"⏱️ Интервал: {CHECK_INTERVAL} секунд")
        print("\nРежимы работы:")
        print("  --interactive  - Интерактивный режим для тестирования")
        print("\nДля интеграции с Max API:")
        print("  1. Настройте webhook endpoint")
        print("  2. Используйте bot.process_message() для обработки входящих")
        print("  3. Реализуйте отправку сообщений через Max API")
        print("=" * 60)
        
        # Держим процесс активным
        try:
            while True:
                # В реальном боте здесь должна быть интеграция с Max API
                # Например, long polling или обработка webhook
                time.sleep(60)
        except KeyboardInterrupt:
            print("\n👋 Остановка бота...")
            bot_monitor.monitor.stop_monitoring()
            sys.exit(0)

if __name__ == "__main__":
    main()