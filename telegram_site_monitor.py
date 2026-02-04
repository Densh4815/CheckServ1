#!/usr/bin/env python3
"""
Telegram бот для мониторинга сайта https://home.borodachev-mikhail.ru/
Разработан для платформы Bothost/Dockhost
"""

import os
import logging
import asyncio
from datetime import datetime, timedelta
from typing import Dict, Any, Optional

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

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Получение токена из переменных окружения
BOT_TOKEN = os.environ.get("TOKEN")
if not BOT_TOKEN:
    logger.error("❌ Токен бота не найден! Установите переменную окружения TOKEN")
    raise ValueError("TOKEN environment variable is required")

# Настройки мониторинга
CHECK_URL = os.environ.get("CHECK_URL", "https://home.borodachev-mikhail.ru/")
CHECK_INTERVAL = int(os.environ.get("CHECK_INTERVAL", "10"))
MAX_CONSECUTIVE_ERRORS = int(os.environ.get("MAX_CONSECUTIVE_ERRORS", "3"))

# Глобальные переменные для мониторинга
monitoring_active = True
site_status = "unknown"
consecutive_errors = 0
stats = {
    'total_checks': 0,
    'successful_checks': 0,
    'failed_checks': 0,
    'start_time': datetime.now(),
    'last_down_time': None,
    'last_up_time': datetime.now(),
    'subscribers': set()  # Множество chat_id подписчиков
}

async def check_website() -> Dict[str, Any]:
    """Проверяет доступность сайта"""
    global site_status, consecutive_errors, stats
    
    stats['total_checks'] += 1
    check_time = datetime.now()
    
    timeout = aiohttp.ClientTimeout(total=10)
    
    try:
        async with aiohttp.ClientSession(timeout=timeout) as session:
            start_time = datetime.now()
            
            async with session.get(CHECK_URL, headers={
                'User-Agent': 'Telegram-Site-Monitor-Bot/1.0'
            }, ssl=False) as response:
                response_time = (datetime.now() - start_time).total_seconds()
                status_code = response.status
                
                if 200 <= status_code < 400:
                    stats['successful_checks'] += 1
                    consecutive_errors = 0
                    
                    if site_status != "up":
                        logger.info(f"✅ Сайт восстановлен")
                    
                    site_status = "up"
                    stats['last_up_time'] = check_time
                    
                    return {
                        'status': 'success',
                        'code': status_code,
                        'response_time': response_time,
                        'message': f"✅ Сайт доступен",
                        'details': f"Код: {status_code}, Время ответа: {response_time:.2f}с",
                        'timestamp': check_time
                    }
                else:
                    stats['failed_checks'] += 1
                    consecutive_errors += 1
                    site_status = "down"
                    
                    if not stats['last_down_time']:
                        stats['last_down_time'] = check_time
                    
                    return {
                        'status': 'error',
                        'code': status_code,
                        'message': f"❌ HTTP ошибка {status_code}",
                        'timestamp': check_time
                    }
                    
    except aiohttp.ClientError as e:
        stats['failed_checks'] += 1
        consecutive_errors += 1
        site_status = "down"
        
        if not stats['last_down_time']:
            stats['last_down_time'] = check_time
        
        return {
            'status': 'error',
            'message': f"❌ Ошибка подключения: {str(e)}",
            'timestamp': check_time
        }
        
    except Exception as e:
        stats['failed_checks'] += 1
        consecutive_errors += 1
        site_status = "down"
        
        if not stats['last_down_time']:
            stats['last_down_time'] = check_time
        
        return {
            'status': 'error',
            'message': f"❌ Неизвестная ошибка: {str(e)}",
            'timestamp': check_time
        }

async def monitoring_task(context: CallbackContext):
    """Фоновая задача для мониторинга сайта"""
    global monitoring_active
    
    logger.info(f"🚀 Запуск мониторинга сайта: {CHECK_URL}")
    logger.info(f"⏱️ Интервал проверки: {CHECK_INTERVAL} секунд")
    
    while monitoring_active:
        try:
            result = await check_website()
            
            if result['status'] == 'success':
                logger.info(f"Проверка #{stats['total_checks']}: {result['message']}")
            else:
                logger.error(f"Проверка #{stats['total_checks']}: {result['message']}")
                
                # Отправляем уведомления подписчикам при ошибках
                if consecutive_errors >= MAX_CONSECUTIVE_ERRORS and stats['subscribers']:
                    message = format_critical_error_message(result)
                    for chat_id in list(stats['subscribers']):
                        try:
                            await context.bot.send_message(
                                chat_id=chat_id,
                                text=message,
                                parse_mode=ParseMode.HTML
                            )
                        except Exception as e:
                            logger.error(f"Ошибка отправки уведомления {chat_id}: {e}")
            
            # Отправляем уведомление о восстановлении
            if result['status'] == 'success' and consecutive_errors == 1 and stats['subscribers']:
                message = format_recovery_message(result)
                for chat_id in list(stats['subscribers']):
                    try:
                        await context.bot.send_message(
                            chat_id=chat_id,
                            text=message,
                            parse_mode=ParseMode.HTML
                        )
                    except Exception as e:
                        logger.error(f"Ошибка отправки восстановления {chat_id}: {e}")
            
            await asyncio.sleep(CHECK_INTERVAL)
            
        except Exception as e:
            logger.error(f"Ошибка в мониторинге: {e}")
            await asyncio.sleep(CHECK_INTERVAL)

def format_critical_error_message(result: Dict[str, Any]) -> str:
    """Форматирует сообщение о критической ошибке"""
    timestamp = result['timestamp'].strftime("%Y-%m-%d %H:%M:%S")
    
    return f"""🚨 <b>КРИТИЧЕСКАЯ ОШИБКА!</b>

🌐 <b>Сайт:</b> {CHECK_URL}
🕒 <b>Время:</b> {timestamp}
🔴 <b>Ошибок подряд:</b> {consecutive_errors}
❌ <b>Ошибка:</b> {result['message']}

🚨 <i>Требуется срочное вмешательство!</i>"""

def format_recovery_message(result: Dict[str, Any]) -> str:
    """Форматирует сообщение о восстановлении"""
    timestamp = result['timestamp'].strftime("%Y-%m-%d %H:%M:%S")
    
    downtime = "неизвестно"
    if stats['last_down_time']:
        downtime_duration = result['timestamp'] - stats['last_down_time']
        downtime = str(downtime_duration).split('.')[0]
    
    return f"""✅ <b>САЙТ ВОССТАНОВЛЕН!</b>

🌐 <b>Сайт:</b> {CHECK_URL}
🕒 <b>Время восстановления:</b> {timestamp}
⏱️ <b>Простой:</b> {downtime}
⚡ <b>Время ответа:</b> {result.get('response_time', 0):.2f}с
📊 <b>Код ответа:</b> {result.get('code', 'N/A')}

🎉 <i>Сайт снова доступен</i>"""

def get_stats() -> Dict[str, Any]:
    """Возвращает статистику мониторинга"""
    uptime = datetime.now() - stats['start_time']
    
    total = stats['total_checks']
    successful = stats['successful_checks']
    
    if total > 0:
        availability = (successful / total) * 100
    else:
        availability = 0
    
    return {
        'site_url': CHECK_URL,
        'current_status': site_status,
        'status_text': "🟢 Доступен" if site_status == "up" else "🔴 Недоступен",
        'uptime': str(uptime).split('.')[0],
        'total_checks': total,
        'successful_checks': successful,
        'failed_checks': stats['failed_checks'],
        'availability_percentage': round(availability, 2),
        'consecutive_errors': consecutive_errors,
        'last_down_time': stats['last_down_time'].strftime("%Y-%m-%d %H:%M:%S") if stats['last_down_time'] else "Нет",
        'last_up_time': stats['last_up_time'].strftime("%Y-%m-%d %H:%M:%S"),
        'monitoring_since': stats['start_time'].strftime("%Y-%m-%d %H:%M:%S"),
        'subscribers_count': len(stats['subscribers']),
        'check_interval': CHECK_INTERVAL
    }

# Обработчики команд
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /start"""
    user = update.effective_user
    chat_id = update.effective_chat.id
    
    welcome_text = f"""🚀 <b>Добро пожаловать в Site Monitor Bot!</b>

👋 Привет, {user.first_name}!

Я отслеживаю доступность сайта:
🌐 {CHECK_URL}

<b>Основные команды:</b>
/status - Текущий статус сайта
/stats - Подробная статистика
/subscribe - Подписаться на уведомления
/unsubscribe - Отписаться от уведомлений
/help - Справка по командам

⚡ <b>Примечание:</b> Автоматическая проверка каждые {CHECK_INTERVAL} секунд

🆔 <b>Ваш ID:</b> {user.id}
👤 <b>Username:</b> @{user.username or 'не указан'}
📅 <b>Дата:</b> {datetime.now().strftime('%d.%m.%Y %H:%M')}"""
    
    await update.message.reply_text(
        welcome_text,
        parse_mode=ParseMode.HTML,
        disable_web_page_preview=True
    )

async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /status"""
    current_stats = get_stats()
    
    if site_status == "up":
        status_message = "✅ Сайт работает стабильно"
    else:
        if consecutive_errors >= MAX_CONSECUTIVE_ERRORS:
            status_message = "🚨 КРИТИЧЕСКАЯ ОШИБКА! Требуется вмешательство!"
        else:
            status_message = "⚠️ Проблемы с доступностью сайта"
    
    response = f"""📊 <b>Текущий статус сайта:</b>

🌐 <b>Сайт:</b> {current_stats['site_url']}
🔄 <b>Статус:</b> {current_stats['status_text']}
⏱️ <b>Последняя проверка:</b> {datetime.now().strftime("%H:%M:%S")}
🔴 <b>Ошибок подряд:</b> {current_stats['consecutive_errors']}

{status_message}"""
    
    await update.message.reply_text(
        response,
        parse_mode=ParseMode.HTML,
        disable_web_page_preview=True
    )

async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /stats"""
    current_stats = get_stats()
    
    response = f"""📈 <b>Статистика мониторинга:</b>

🌐 <b>Сайт:</b> {current_stats['site_url']}
⏱️ <b>Аптайм:</b> {current_stats['uptime']}
🔄 <b>Всего проверок:</b> {current_stats['total_checks']}
✅ <b>Успешно:</b> {current_stats['successful_checks']}
❌ <b>Ошибок:</b> {current_stats['failed_checks']}
📊 <b>Доступность:</b> {current_stats['availability_percentage']}%
👥 <b>Подписчиков:</b> {current_stats['subscribers_count']}

⏰ <b>Последний сбой:</b> {current_stats['last_down_time']}
🕒 <b>Работает с:</b> {current_stats['monitoring_since']}"""
    
    await update.message.reply_text(
        response,
        parse_mode=ParseMode.HTML,
        disable_web_page_preview=True
    )

async def subscribe_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /subscribe"""
    chat_id = update.effective_chat.id
    
    if chat_id in stats['subscribers']:
        await update.message.reply_text(
            "❌ Вы уже подписаны на уведомления!",
            parse_mode=ParseMode.HTML
        )
        return
    
    stats['subscribers'].add(chat_id)
    await update.message.reply_text(
        "✅ Вы успешно подписались на уведомления!\n\n"
        "Вы будете получать сообщения при:\n"
        "• Критических ошибках сайта\n"
        "• Восстановлении работы сайта",
        parse_mode=ParseMode.HTML
    )

async def unsubscribe_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /unsubscribe"""
    chat_id = update.effective_chat.id
    
    if chat_id not in stats['subscribers']:
        await update.message.reply_text(
            "❌ Вы не подписаны на уведомления!",
            parse_mode=ParseMode.HTML
        )
        return
    
    stats['subscribers'].remove(chat_id)
    await update.message.reply_text(
        "✅ Вы отписались от уведомлений.\n\n"
        "Больше не будете получать сообщения о проблемах с сайтом.",
        parse_mode=ParseMode.HTML
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /help"""
    help_text = f"""ℹ️ <b>Справка по командам:</b>

<b>Основные команды:</b>
/start - Начало работы с ботом
/status - Текущий статус сайта
/stats - Подробная статистика мониторинга
/subscribe - Подписаться на уведомления
/unsubscribe - Отписаться от уведомлений
/help - Эта справка

<b>Информация о мониторинге:</b>
• Сайт проверяется каждые {CHECK_INTERVAL} секунд
• Уведомления отправляются при сбоях
• Статистика обновляется в реальном времени
• Бот работает 24/7

🌐 <b>Мониторим:</b> {CHECK_URL}"""
    
    await update.message.reply_text(
        help_text,
        parse_mode=ParseMode.HTML,
        disable_web_page_preview=True
    )

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик текстовых сообщений"""
    text = update.message.text.lower()
    
    if text in ['привет', 'hello', 'hi', 'здравствуй']:
        await update.message.reply_text(
            f"👋 Привет! Я бот для мониторинга сайтов.\n\n"
            f"Я отслеживаю доступность сайта {CHECK_URL}.\n\n"
            f"Напишите /help для списка команд или /status для проверки текущего состояния.",
            parse_mode=ParseMode.HTML
        )
    elif text in ['пока', 'до свидания', 'bye', 'goodbye']:
        await update.message.reply_text(
            "👋 До свидания! Надеюсь, сайт будет стабильным!\n\n"
            "Не забывайте проверять статус командой /status",
            parse_mode=ParseMode.HTML
        )
    else:
        await update.message.reply_text(
            "🤔 Я не понял ваше сообщение.\n\n"
            "Попробуйте одну из команд:\n"
            "• /start - Начало работы\n"
            "• /status - Статус сайта\n"
            "• /stats - Статистика\n"
            "• /help - Справка",
            parse_mode=ParseMode.HTML
        )

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик ошибок"""
    logger.error(f"Ошибка при обработке обновления: {context.error}")
    
    if update and update.effective_chat:
        try:
            await update.effective_chat.send_message(
                "⚠️ Произошла ошибка при обработке вашего запроса. Пожалуйста, попробуйте позже."
            )
        except:
            pass

async def post_init(application: Application):
    """Функция, выполняемая после инициализации бота"""
    # Запускаем задачу мониторинга
    job_queue = application.job_queue
    job_queue.run_once(lambda ctx: asyncio.create_task(monitoring_task(ctx)), when=5)
    
    logger.info("🤖 Бот инициализирован и готов к работе!")
    logger.info(f"🌐 Мониторинг сайта: {CHECK_URL}")
    logger.info(f"⏱️ Интервал проверки: {CHECK_INTERVAL} сек")

def main():
    """Основная функция запуска бота"""
    logger.info(f"🚀 Запуск Telegram бота для мониторинга сайта...")
    logger.info(f"🌐 Сайт: {CHECK_URL}")
    logger.info(f"⏱️ Интервал: {CHECK_INTERVAL} секунд")
    
    # Создаем приложение
    application = Application.builder().token(BOT_TOKEN).post_init(post_init).build()
    
    # Регистрируем обработчики команд
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("status", status_command))
    application.add_handler(CommandHandler("stats", stats_command))
    application.add_handler(CommandHandler("subscribe", subscribe_command))
    application.add_handler(CommandHandler("unsubscribe", unsubscribe_command))
    application.add_handler(CommandHandler("help", help_command))
    
    # Регистрируем обработчик текстовых сообщений
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    # Регистрируем обработчик ошибок
    application.add_error_handler(error_handler)
    
    # Запускаем бота
    logger.info("✅ Бот запущен. Нажмите Ctrl+C для остановки.")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
