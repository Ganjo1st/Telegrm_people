import sqlite3
import logging
from typing import Optional, Tuple

DB_PATH = "pr_bot.db"

def init_db():
    """Инициализация базы данных и создание таблиц."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Таблица пользователей
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            channel_link TEXT,
            channel_id TEXT,
            points INTEGER DEFAULT 0
        )
    ''')
    
    # Таблица для отслеживания выполненных заданий (чтобы не показывать одно и то же)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS completed_tasks (
            user_id INTEGER,
            target_channel_id TEXT,
            PRIMARY KEY (user_id, target_channel_id)
        )
    ''')
    
    conn.commit()
    conn.close()
    logging.info("База данных инициализирована.")

def get_user(user_id: int) -> Optional[Tuple]:
    """Получает данные пользователя по его ID."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
    user = cursor.fetchone()
    conn.close()
    return user

def register_user(user_id: int, username: str):
    """Регистрирует нового пользователя, если его еще нет."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    try:
        cursor.execute("INSERT OR IGNORE INTO users (user_id, username) VALUES (?, ?)", (user_id, username))
        conn.commit()
    except Exception as e:
        logging.error(f"Ошибка при регистрации пользователя: {e}")
    finally:
        conn.close()

def add_channel(user_id: int, channel_link: str, channel_id: str):
    """Сохраняет канал пользователя для участия в ВП."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    # Обновляем данные пользователя и начисляем 10 баллов за добавление канала
    cursor.execute(
        "UPDATE users SET channel_link = ?, channel_id = ?, points = points + 10 WHERE user_id = ?",
        (channel_link, channel_id, user_id)
    )
    conn.commit()
    conn.close()

def get_random_channel_for_user(user_id: int) -> Optional[Tuple[str, str, int]]:
    """
    Выбирает случайный канал из базы для показа пользователю.
    Исключает его собственный канал и каналы, на которые он уже подписывался.
    """
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    query = '''
        SELECT channel_link, channel_id, user_id 
        FROM users 
        WHERE channel_link IS NOT NULL 
          AND user_id != ? 
          AND user_id NOT IN (
              SELECT target_channel_id FROM completed_tasks WHERE user_id = ?
          )
        ORDER BY RANDOM() LIMIT 1
    '''
    # ВАЖНО: В таблице completed_tasks мы храним user_id того, кто выполнил, и target_channel_id
    # Но в запросе выше мы сравниваем user_id с target_channel_id. Исправим логику:
    
    # Правильный запрос: ищем каналы других пользователей, которые текущий юзер еще не выполнял
    query = '''
        SELECT u.channel_link, u.channel_id, u.user_id 
        FROM users u
        WHERE u.channel_link IS NOT NULL 
          AND u.user_id != ? 
          AND u.channel_id NOT IN (
              SELECT target_channel_id FROM completed_tasks WHERE user_id = ?
          )
        ORDER BY RANDOM() LIMIT 1
    '''
    
    cursor.execute(query, (user_id, user_id))
    row = cursor.fetchone()
    conn.close()
    return row

def mark_task_completed(user_id: int, target_channel_id: str):
    """Отмечает задание как выполненное и начисляет баллы за подписку."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    try:
        # Записываем в выполненные
        cursor.execute(
            "INSERT OR IGNORE INTO completed_tasks (user_id, target_channel_id) VALUES (?, ?)",
            (user_id, target_channel_id)
        )
        # Начисляем 5 баллов за выполнение задания
        cursor.execute("UPDATE users SET points = points + 5 WHERE user_id = ?", (user_id,))
        conn.commit()
    except Exception as e:
        logging.error(f"Ошибка при отметке задания: {e}")
    finally:
        conn.close()
