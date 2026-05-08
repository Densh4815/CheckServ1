#!/usr/bin/env python3
"""
УПРОЩЕННЫЙ Telegram бот для мониторинга сайта
Использует системные переменные окружения Bothost
Работает на бесплатном тарифе
"""

import os
import sys
import time
import logging
import asyncio
from datetime import datetime
from typing import Dict, Any, Set

import aiohttp
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes,
    CallbackContext
)
from telegram.constants import ParseMode

# ========== КОНФИГУРАЦИЯ ИЗ СИСТЕМНЫХ ПЕРЕМЕННЫХ ==========

# Токен берем из системных переменных Bothost (они уже есть!)
BOT_TOKEN = os.environ.get("TOKEN") or os.environ.get("TELEGRAM_BOT_TOKEN") or os.environ.get("BOT_TOKEN")

if not BOT_TOKEN:
    logging.error("❌ Токен бота не найден в системных переменных!")
    sys.exit(1)

# URL для мониторинга (можно жестко задать или через файл)
CHECK_URL = "https://home.borodachev-mikhail.ru/"
CHECK_INTERVAL = 10  # секунд
MAX_CONSECUTIVE_ERRORS = 3

# ========== НАСТРОЙКА ЛОГИРОВАНИЯ ==========

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ========== ГЛОБАЛЬНЫЕ ПЕРЕМЕННЫЕ ==========

monitoring_active = True
site_status = "unknown"
consecutive_errors = 0
subscribers: Set[int] = set()  # Множество chat_id подписчиков
already_notified_down = False  # Флаг, что уведомление о сбое уже отправлено
downtime_start: datetime = None  # Время начала простоя

# Статистика
stats = {
    'total_checks': 0,
    'successful_checks': 0,
    'failed_checks': 0,
    'start_time': datetime.now(),
    'last_down_time': None,
    'last_up_time': datetime.now(),
}

# ========== ФУНКЦИИ МОНИТОРИНГА ==========

async def check_website() -> Dict[str, Any]:
    """Проверяет доступность сайта"""
    global site_status, consecutive_errors, stats, already_notified_down, downtime_start
    
    stats['total_checks'] += 1
    check_time = datetime.now()
    
    timeout = aiohttp.ClientTimeout(total=10)
    
    try:
        async with aiohttp.ClientSession(timeout=timeout) as session:
            start_time = datetime.now()
            
            async with session.get(CHECK_URL, headers={
                'User-Agent': 'Site-Monitor-Bot/1.0'
            }, ssl=False) as response:
                response_time = (datetime.now() - start_time).total_seconds()
                status_code = response.status
                
                if 200 <= status_code < 400:
                    stats['successful_checks'] += 1
                    site_status = "up"
                    stats['last_up_time'] = check_time
                    
                    # Если были ошибки, сбрасываем счетчик
                    if consecutive_errors > 0:
                        consecutive_errors = 0
                        logger.info(f"✅ Восстановление после {stats['failed_checks']} ошибок")
                    
                    logger.info(f"✅ Проверка #{stats['total_checks']}: Сайт доступен (код: {status_code})")
                    
                    return {
                        'status': 'success',
                        'code': status_code,
                        'response_time': response_time,
                        'message': f"✅ Сайт доступен",
                        'timestamp': check_time,
                        'recovered': already_notified_down  # Флаг восстановления после уведомления
                    }
                else:
                    stats['failed_checks'] += 1
                    consecutive_errors += 1
                    site_status = "down"
                    
                    # Запоминаем время начала простоя
                    if not downtime_start:
                        downtime_start = check_time
                    
                    if not stats['last_down_time']:
                        stats['last_down_time'] = check_time
                    
                    logger.error(f"❌ Проверка #{stats['total_checks']}: HTTP ошибка {status_code}")
                    
                    return {
                        'status': 'error',
                        'code': status_code,
                        'message': f"❌ HTTP ошибка {status_code}",
                        'timestamp': check_time,
                        'consecutive_errors': consecutive_errors
                    }
                    
    except Exception as e:
        stats['failed_checks'] += 1
        consecutive_errors += 1
        site_status = "down"
        
        # Запоминаем время начала простоя
        if not downtime_start:
            downtime_start = datetime.now()
        
        if not stats['last_down_time']:
            stats['last_down_time'] = datetime.now()
        
        logger.error(f"❌ Проверка #{stats['total_checks']}: Ошибка подключения - {str(e)}")
        
        return {
            'status': 'error',
            'message': f"❌ Ошибка подключения: {str(e)}",
            'timestamp': datetime.now(),
            'consecutive_errors': consecutive_errors
        }

async def monitoring_task(context: CallbackContext):
    """Фоновая задача для мониторинга сайта"""
    global monitoring_active, already_notified_down, downtime_start
    
    logger.info(f"🚀 Запуск мониторинга: {CHECK_URL}")
    logger.info(f"⏱️ Интервал проверки: {CHECK_INTERVAL} секунд")
    
    while monitoring_active:
        try:
            result = await check_website()
            
            # Отправляем ОДНО уведомление о сбое при достижении критического уровня
            if (result['status'] == 'error' and 
                result.get('consecutive_errors', 0) >= MAX_CONSECUTIVE_ERRORS and
                not already_notified_down):
                
                if subscribers:
                    message = format_critical_error_message(result)
                    for chat_id in list(subscribers):
                        try:
                            await context.bot.send_message(
                                chat_id=chat_id,
                                text=message,
                                parse_mode=ParseMode.HTML
                            )
                        except Exception as e:
                            logger.error(f"Ошибка отправки уведомления {chat_id}: {e}")
                    
                    # Устанавливаем флаг, что уведомление отправлено
                    already_notified_down = True
                    logger.info(f"🚨 Отправлено уведомление о сбое {len(subscribers)} подписчикам")
            
            # Отправляем ОДНО уведомление о восстановлении
            elif (result['status'] == 'success' and 
                  already_notified_down and 
                  result.get('recovered', False)):
                
                if subscribers:
                    message = format_recovery_message(result)
                    for chat_id in list(subscribers):
                        try:
                            await context.bot.send_message(
                                chat_id=chat_id,
                                text=message,
                                parse_mode=ParseMode.HTML
                            )
                        except Exception as e:
                            logger.error(f"Ошибка отправки восстановления {chat_id}: {e}")
                    
                    # Сбрасываем флаги после восстановления
                    already_notified_down = False
                    downtime_start = None
                    logger.info(f"✅ Отправлено уведомление о восстановлении {len(subscribers)} подписчикам")
            
            await asyncio.sleep(CHECK_INTERVAL)
            
        except Exception as e:
            logger.error(f"Ошибка в мониторинге: {e}")
            await asyncio.sleep(CHECK_INTERVAL)

def format_critical_error_message(result: Dict[str, Any]) -> str:
    """Форматирует сообщение о критической ошибке"""
    timestamp = result['timestamp'].strftime("%Y-%m-%d %H:%M:%S")
    consecutive = result.get('consecutive_errors', 0)
    
    return f"""🚨 <b>САЙТ НЕДОСТУПЕН!</b>

🌐 <b>Сайт:</b> {CHECK_URL}
🕒 <b>Время сбоя:</b> {timestamp}
🔴 <b>Ошибок подряд:</b> {consecutive}

❌ <b>Причина:</b> {result['message']}

<i>Бот продолжит мониторинг. Вы получите уведомление при восстановлении.</i>"""

def format_recovery_message(result: Dict[str, Any]) -> str:
    """Форматирует сообщение о восстановлении"""
    global downtime_start
    
    timestamp = result['timestamp'].strftime("%Y-%m-%d %H:%M:%S")
    
    downtime = "неизвестно"
    if downtime_start:
        downtime_duration = result['timestamp'] - downtime_start
        downtime = str(downtime_duration).split('.')[0]
    
    return f"""✅ <b>САЙТ ВОССТАНОВЛЕН!</b>

🌐 <b>Сайт:</b> {CHECK_URL}
🕒 <b>Время восстановления:</b> {timestamp}
⏱️ <b>Общий простой:</b> {downtime}
📊 <b>Ответ сервера:</b> {result.get('code', 'N/A')} ({result.get('response_time', 0):.2f} сек)

🎉 <i>Мониторинг продолжается в обычном режиме</i>"""

def get_stats() -> Dict[str, Any]:
    """Возвращает статистику мониторинга"""
    uptime = datetime.now() - stats['start_time']
    
    total = stats['total_checks']
    successful = stats['successful_checks']
    
    if total > 0:
        availability = (successful / total) * 100
    else:
        availability = 0
    
    status_text = "🟢 Доступен"
    if site_status == "down":
        if already_notified_down:
            status_text = "🔴 КРИТИЧЕСКИЙ СБОЙ (уведомление отправлено)"
        else:
            status_text = "🟡 Проблемы (мониторинг)"
    
    return {
        'site_url': CHECK_URL,
        'status': status_text,
        'uptime': str(uptime).split('.')[0],
        'total_checks': total,
        'successful_checks': successful,
        'failed_checks': stats['failed_checks'],
        'availability': f"{availability:.1f}%",
        'errors_count': consecutive_errors,
        'subscribers': len(subscribers),
        'last_check': datetime.now().strftime("%H:%M:%S"),
        'notified_down': already_notified_down
    }

# ========== ОБРАБОТЧИКИ КОМАНД БОТА ==========

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /start"""
    user = update.effective_user
    
    await update.message.reply_text(
        f"""🚀 <b>Site Monitor Bot активирован!</b>

👋 Привет, {user.first_name}!

Я отслеживаю доступность сайта:
🌐 {CHECK_URL}

<b>Основные команды:</b>
/status - Текущий статус сайта
/stats - Подробная статистика
/subscribe - Подписаться на уведомления
/unsubscribe - Отписаться от уведомлений
/help - Справка по командам

<b>Уведомления:</b>
• 📨 Одно сообщение при сбое (после {MAX_CONSECUTIVE_ERRORS} ошибок)
• ✅ Одно сообщение при восстановлении
• 🔕 Без спама - только важные события

🆔 <b>Ваш ID:</b> <code>{user.id}</code>
📅 <b>Дата:</b> {datetime.now().strftime('%d.%m.%Y %H:%M')}""",
        parse_mode=ParseMode.HTML,
        disable_web_page_preview=True
    )

async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /status"""
    current_stats = get_stats()
    
    if site_status == "up":
        if already_notified_down:
            status_msg = "✅ Сайт восстановлен после сбоя"
        else:
            status_msg = "✅ Сайт работает стабильно"
    elif already_notified_down:
        status_msg = f"🚨 КРИТИЧЕСКИЙ СБОЙ! Уведомление отправлено ({consecutive_errors} ошибок)"
    else:
        status_msg = f"⚠️ Проблемы ({consecutive_errors}/{MAX_CONSECUTIVE_ERRORS} ошибок)"
    
    await update.message.reply_text(
        f"""📊 <b>Текущий статус:</b>

🌐 Сайт: {CHECK_URL}
🔄 Статус: {current_stats['status']}
⏱️ Последняя проверка: {current_stats['last_check']}
🔴 Ошибок подряд: {consecutive_errors}/{MAX_CONSECUTIVE_ERRORS}

{status_msg}""",
        parse_mode=ParseMode.HTML,
        disable_web_page_preview=True
    )

async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /stats"""
    current_stats = get_stats()
    
    notification_status = "✅ Уведомление отправлено" if current_stats['notified_down'] else "⏳ Ожидание критического уровня"
    
    await update.message.reply_text(
        f"""📈 <b>Статистика мониторинга:</b>

🌐 Сайт: {CHECK_URL}
⏱️ Аптайм: {current_stats['uptime']}
🔄 Проверок: {current_stats['total_checks']}
✅ Успешно: {current_stats['successful_checks']}
❌ Ошибок: {current_stats['failed_checks']}
📊 Доступность: {current_stats['availability']}
👥 Подписчиков: {current_stats['subscribers']}

<b>Текущее состояние:</b>
🔢 Ошибок подряд: {current_stats['errors_count']}/{MAX_CONSECUTIVE_ERRORS}
🔔 Статус уведомлений: {notification_status}

⏰ Интервал: {CHECK_INTERVAL} секунд""",
        parse_mode=ParseMode.HTML,
        disable_web_page_preview=True
    )

async def subscribe_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /subscribe"""
    chat_id = update.effective_chat.id
    
    if chat_id in subscribers:
        await update.message.reply_text(
            "❌ Вы уже подписаны на уведомления!",
            parse_mode=ParseMode.HTML
        )
        return
    
    subscribers.add(chat_id)
    await update.message.reply_text(
        f"""✅ Вы подписались на уведомления!

📨 <b>Вы будете получать:</b>
• Одно сообщение при сбое (после {MAX_CONSECUTIVE_ERRORS} ошибок подряд)
• Одно сообщение при восстановлении работы сайта
• Никакого спама - только важные события

👥 Всего подписчиков: {len(subscribers)}""",
        parse_mode=ParseMode.HTML
    )

async def unsubscribe_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /unsubscribe"""
    chat_id = update.effective_chat.id
    
    if chat_id not in subscribers:
        await update.message.reply_text(
            "❌ Вы не подписаны на уведомления!",
            parse_mode=ParseMode.HTML
        )
        return
    
    subscribers.remove(chat_id)
    await update.message.reply_text(
        "✅ Вы отписались от уведомлений.",
        parse_mode=ParseMode.HTML
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /help"""
    await update.message.reply_text(
        f"""ℹ️ <b>Справка по командам:</b>

<b>Основные команды:</b>
/start - Начало работы
/status - Текущий статус сайта
/stats - Подробная статистика
/subscribe - Подписаться на уведомления
/unsubscribe - Отписаться
/help - Эта справка

<b>Как работают уведомления:</b>
1. Бот молча проверяет сайт каждые {CHECK_INTERVAL} секунд
2. При {MAX_CONSECUTIVE_ERRORS} ошибках подряд - одно уведомление всем подписчикам
3. После восстановления - одно уведомление о восстановлении
4. Далее бот снова молчит до следующего критического сбоя

<b>Информация:</b>
• Сайт: {CHECK_URL}
• Интервал проверки: {CHECK_INTERVAL} секунд
• Критический уровень: {MAX_CONSECUTIVE_ERRORS} ошибок подряд""",
        parse_mode=ParseMode.HTML,
        disable_web_page_preview=True
    )

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка обычных сообщений"""
    text = update.message.text.lower()
    
    if text in ['привет', 'hello', 'hi', 'здравствуй']:
        await update.message.reply_text(
            f"👋 Привет! Я бот для мониторинга сайта {CHECK_URL}\n\n"
            f"Я работаю тихо - отправляю уведомления только при серьезных проблемах.\n"
            f"Напишите /help для списка команд",
            parse_mode=ParseMode.HTML
        )
    elif text in ['пока', 'до свидания', 'bye']:
        await update.message.reply_text(
            "👋 До свидания! Надеюсь, сайт будет стабильным!",
            parse_mode=ParseMode.HTML
        )
    else:
        await update.message.reply_text(
            "🤔 Я не понял сообщение. Используйте команды:\n"
            "/start, /status, /stats, /help",
            parse_mode=ParseMode.HTML
        )

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик ошибок"""
    logger.error(f"Ошибка: {context.error}")

# ========== ОСНОВНАЯ ФУНКЦИЯ ==========

async def post_init(application: Application):
    """Выполняется после инициализации бота"""
    # Запускаем мониторинг
    job_queue = application.job_queue
    job_queue.run_once(lambda ctx: asyncio.create_task(monitoring_task(ctx)), when=3)
    
    logger.info("=" * 60)
    logger.info("🤖 БОТ ЗАПУЩЕН НА BOTHOST")
    logger.info("=" * 60)
    logger.info(f"🌐 Мониторинг сайта: {CHECK_URL}")
    logger.info(f"⏱️ Интервал проверки: {CHECK_INTERVAL} сек")
    logger.info(f"🚨 Критический уровень: {MAX_CONSECUTIVE_ERRORS} ошибок подряд")
    logger.info(f"🔑 Токен бота: ***{BOT_TOKEN[-8:]}")
    logger.info("=" * 60)
    logger.info("✅ Бот готов к работе! Работает в тихом режиме.")
    logger.info("=" * 60)

def main():
    """Точка входа в программу"""
    # Проверяем наличие токена
    if not BOT_TOKEN:
        logger.error("❌ Токен бота не найден!")
        logger.info("ℹ️ Bothost должен автоматически установить переменные TOKEN, TELEGRAM_BOT_TOKEN")
        return
    
    logger.info(f"🚀 Запуск Site Monitor Bot...")
    logger.info(f"🌐 Сайт для мониторинга: {CHECK_URL}")
    logger.info(f"🔕 Режим: тихий (уведомления только при критических сбоях)")
    
    try:
        # Создаем приложение бота
        application = Application.builder().token(BOT_TOKEN).post_init(post_init).build()
        
        # Регистрируем обработчики команд
        application.add_handler(CommandHandler("start", start_command))
        application.add_handler(CommandHandler("status", status_command))
        application.add_handler(CommandHandler("stats", stats_command))
        application.add_handler(CommandHandler("subscribe", subscribe_command))
        application.add_handler(CommandHandler("unsubscribe", unsubscribe_command))
        application.add_handler(CommandHandler("help", help_command))
        
        # Обработчик обычных сообщений
        application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
        
        # Обработчик ошибок
        application.add_error_handler(error_handler)
        
        # Запускаем бота
        logger.info("✅ Бот запущен. Используйте Ctrl+C для остановки.")
        application.run_polling(allowed_updates=Update.ALL_TYPES, drop_pending_updates=True)
        
    except Exception as e:
        logger.error(f"❌ Критическая ошибка: {e}")
        if "Invalid token" in str(e) or "Unauthorized" in str(e):
            logger.error("⚠️ Неверный токен бота! Проверьте системные переменные Bothost.")

if __name__ == "__main__":
    main()
