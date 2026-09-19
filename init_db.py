import sqlite3
conn = sqlite3.connect('/opt/pristmax/data/tasks.db')

conn.execute('''CREATE TABLE IF NOT EXISTS tasks (
    task_id TEXT PRIMARY KEY,
    task_type TEXT NOT NULL,
    user_id TEXT NOT NULL,
    input_path TEXT,
    output_path TEXT,
    params TEXT,
    status TEXT,
    priority INTEGER,
    result TEXT,
    error TEXT,
    progress REAL,
    progress_message TEXT,
    created_at TEXT,
    started_at TEXT,
    completed_at TEXT,
    retry_count INTEGER,
    max_retries INTEGER)''')

conn.execute('''CREATE TABLE IF NOT EXISTS strategies (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    type TEXT NOT NULL,
    crf INTEGER DEFAULT 28,
    preset TEXT DEFAULT 'medium',
    enabled INTEGER DEFAULT 1,
    config TEXT DEFAULT '{}',
    created_at TEXT,
    updated_at TEXT)''')

conn.execute('''CREATE TABLE IF NOT EXISTS alert_history (
    alert_id TEXT PRIMARY KEY,
    level TEXT NOT NULL,
    title TEXT NOT NULL,
    message TEXT,
    metric TEXT,
    value REAL,
    threshold REAL,
    timestamp TEXT,
    acknowledged INTEGER DEFAULT 0,
    acknowledged_by TEXT,
    acknowledged_at TEXT)''')

conn.execute('''CREATE TABLE IF NOT EXISTS notification_channels (
    id TEXT PRIMARY KEY,
    type TEXT NOT NULL,
    name TEXT NOT NULL,
    config TEXT NOT NULL DEFAULT '{}',
    enabled INTEGER DEFAULT 1,
    created_at TEXT)''')

conn.execute('''CREATE TABLE IF NOT EXISTS notification_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    channel_id TEXT,
    alert_id TEXT,
    level TEXT,
    title TEXT,
    status TEXT,
    error TEXT,
    sent_at TEXT)''')

conn.commit()
conn.close()
print('Tables created')
