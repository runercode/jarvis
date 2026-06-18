import sqlite3

DB_NAME = "jarvis.db"

def init_db():
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()

    c.execute("""
    CREATE TABLE IF NOT EXISTS memories (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              content TEXT
              
    )
    """)

    conn.commit()
    conn.close()


def add_memory(text):
    conn = sqlite3.connect(DB_NAME) 
    c = conn.cursor()

    c.execute("INSERT INTO memories (content) VALUES (?)", (text,))
    conn.commit()
    conn.close

def get_memories():
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()

    c.execute("SELECT content FROM memories ORDER BY id DESC")
    rows = c.fetchall()

    conn.close()
    return [r[0] for r in rows]   