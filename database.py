import sqlite3
import logging
from typing import Optional, Tuple

DB_PATH = "pr_bot.db"

def init_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            channel_link TEXT,
            channel_id TEXT,
            points INTEGER DEFAULT 0,
            is_active INTEGER DEFAULT 1
        )
    ''')
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
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
    user = cursor.fetchone()
    conn.close()
    return user

def get_user_by_channel(channel_id: str) -> Optional[Tuple]:
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE channel_id = ?", (channel_id,))
    user = cursor.fetchone()
    conn.close()
    return user

def register_user(user_id: int, username: str):
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
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE users SET channel_link = ?, channel_id = ?, points = points + 10, is_active = 1 WHERE user_id = ?",
        (channel_link, channel_id, user_id)
    )
    conn.commit()
    conn.close()

def mark_channel_inactive(user_id: int):
    """Помечает канал как неактивный (удален или бот заблокирован)."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET is_active = 0 WHERE user_id = ?", (user_id,))
    conn.commit()
    conn.close()

def get_random_channel_for_user(user_id: int) -> Optional[Tuple[str, str, int]]:
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    # Ищем только активные каналы
    query = '''
        SELECT u.channel_link, u.channel_id, u.user_id, u.points
        FROM users u
        WHERE u.channel_link IS NOT NULL 
          AND u.points > 0 
          AND u.is_active = 1
          AND u.user_id != ? 
          AND u.channel_id NOT IN (
              SELECT target_channel_id FROM completed_tasks WHERE user_id = ?
          )
        ORDER BY u.points DESC, RANDOM() LIMIT 1
    '''
    cursor.execute(query, (user_id, user_id))
    row = cursor.fetchone()
    if row:
        channel_link, channel_id, owner_id, points = row
        cursor.execute("UPDATE users SET points = points - 1 WHERE user_id = ?", (owner_id,))
        conn.commit()
    conn.close()
    return (row[0], row[1], row[2]) if row else None

def mark_task_completed(user_id: int, target_channel_id: str):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    try:
        cursor.execute(
            "INSERT OR IGNORE INTO completed_tasks (user_id, target_channel_id) VALUES (?, ?)",
            (user_id, target_channel_id)
        )
        cursor.execute("UPDATE users SET points = points + 5 WHERE user_id = ?", (user_id,))
        conn.commit()
    except Exception as e:
        logging.error(f"Ошибка при отметке задания: {e}")
    finally:
        conn.close()
