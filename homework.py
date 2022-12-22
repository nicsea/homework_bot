import logging
import os
import time

import requests
import telegram

from dotenv import load_dotenv
from logging.config import fileConfig

load_dotenv()

fileConfig('logging_config.ini')
logger = logging.getLogger()

PRACTICUM_TOKEN = os.getenv('PRACTICUM_TOKEN')
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')

RETRY_PERIOD = 600
ENDPOINT = 'https://practicum.yandex.ru/api/user_api/homework_statuses/'
HEADERS = {'Authorization': f'OAuth {PRACTICUM_TOKEN}'}

HOMEWORK_VERDICTS = {
    'approved': 'Работа проверена: ревьюеру всё понравилось. Ура!',
    'reviewing': 'Работа взята на проверку ревьюером.',
    'rejected': 'Работа проверена: у ревьюера есть замечания.'
}

homework_statuses = {}
errors_sent_to_telegram = set()
ALLOWED_STATUSES = ('approved', 'reviewing', 'rejected')


def check_tokens():
    """Проверка наличия обязательных токенов."""
    tokens = {'PRACTICUM_TOKEN': PRACTICUM_TOKEN,
              'TELEGRAM_TOKEN': TELEGRAM_TOKEN,
              'TELEGRAM_CHAT_ID': TELEGRAM_CHAT_ID}
    for token, value in tokens.items():
        if not value:
            message = f'Не найден токен: {token}. Работа программы завершена'
            logger.critical(message)
            raise SystemExit
    return True


def send_message(bot, message):
    """Отправка сообщения в Telegram."""
    try:
        bot.send_message(TELEGRAM_CHAT_ID, message)
        logger.debug(f'Сообщение отравлено: {message}')
    except telegram.error.TelegramError:
        logger.error(f'Сообщение не отравлено: {message}')


def get_api_answer(timestamp):
    """Получение информации по API."""
    try:
        payload = {'from_date': timestamp}
        statuses = requests.get(ENDPOINT, headers=HEADERS, params=payload)
    except requests.exceptions.RequestException:
        raise Exception
    status_code = statuses.status_code
    if status_code != 200:
        message = f'Не получен ответ от сервера. ' \
                  f'Код ответа: {status_code}. '
        raise Exception(message)
    return statuses.json()


def check_response(response):
    """Проверка изменения статуса домашней работы."""
    if not isinstance(response, dict):
        raise TypeError
    if 'homeworks' not in response:
        raise TypeError
    if not isinstance(response['homeworks'], list):
        raise TypeError


def parse_status(homework):
    """Проверка изменения статуса домашней работы."""
    homework_name = homework.get('homework_name')
    if homework_name is None:
        raise Exception('В ответе сервера нет ключа homework_name')
    status = homework.get('status')
    if status not in ALLOWED_STATUSES:
        raise Exception(f'Неизвестный статус {status}')
    old_status = homework_statuses.get(homework_name)
    if status == old_status:
        logger.debug(f'Статус проверки {homework_name} не изменился')
        return ''
    if old_status is None:
        homework_statuses[homework_name] = status
    verdict = HOMEWORK_VERDICTS.get(status)
    return f'Изменился статус проверки работы "{homework_name}". {verdict}'


def process_exception(bot, message):
    """Обработка исключения. Логирование и уведомление в Telegram."""
    message += f'Повторный запрос через {RETRY_PERIOD} секунд.'
    logger.error(message)
    if message not in errors_sent_to_telegram:
        send_message(bot, message)
        errors_sent_to_telegram.add(message)
    time.sleep(RETRY_PERIOD)


def main():
    """Основная логика работы бота."""
    check_tokens()
    bot = telegram.Bot(token=TELEGRAM_TOKEN)
    timestamp = int(time.time())
    while True:
        try:
            answer = get_api_answer(timestamp)
            check_response(answer)
            homeworks = answer.get('homeworks')
            for homework in homeworks:
                message = parse_status(homework)
                if message:
                    send_message(bot, message)
            if not homeworks:
                logger.debug('Нет домашних работ в проверке')
            time.sleep(RETRY_PERIOD)
        except TypeError:
            message = 'Получен некорректный ответ от сервера. '
            process_exception(bot, message)
        except Exception as error:
            message = f'Сбой в работе программы: {error} '
            process_exception(bot, message)


if __name__ == '__main__':
    main()
