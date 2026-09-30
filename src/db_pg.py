import os

import psycopg2
import psycopg2.extras

DB_CONFIG = {
    "host": os.environ.get("DB_HOST", "postgres"),
    "port": int(os.environ.get("DB_PORT", 5432)),
    "user": os.environ.get("DB_USERNAME", "coaching"),
    "password": os.environ.get("DB_PASSWORD", "coaching_pwd_2026"),
    "dbname": os.environ.get("DB_NAME", "coaching"),
}


def get_db():
    conn = psycopg2.connect(**DB_CONFIG)
    conn.autocommit = True
    return conn


def dict_cursor(conn):
    return conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)


def init_db():
    conn = get_db()
    c = conn.cursor()

    c.execute("""CREATE TABLE IF NOT EXISTS coach (
        id SERIAL PRIMARY KEY,
        username VARCHAR(100) UNIQUE NOT NULL,
        password_hash VARCHAR(255) NOT NULL,
        name VARCHAR(200) NOT NULL,
        timezone VARCHAR(64) DEFAULT 'Europe/London',
        logo_path VARCHAR(500),
        accent_color VARCHAR(20) DEFAULT '#e94560',
        bg_color VARCHAR(20) DEFAULT '#1a1a2e',
        card_color VARCHAR(20) DEFAULT '#16213e',
        telegram_bot_token VARCHAR(200),
        is_admin SMALLINT DEFAULT 0,
        status VARCHAR(20) DEFAULT 'active',
        email VARCHAR(200),
        features JSONB,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )""")

    c.execute("""CREATE TABLE IF NOT EXISTS coachee (
        id SERIAL PRIMARY KEY,
        username VARCHAR(100) UNIQUE NOT NULL,
        password_hash VARCHAR(255) NOT NULL,
        name VARCHAR(200) NOT NULL,
        coach_id INT NOT NULL REFERENCES coach(id),
        contract_text TEXT,
        safe_word VARCHAR(100) DEFAULT 'RED',
        status VARCHAR(20) DEFAULT 'active',
        task_unveil_time TIME DEFAULT '08:00:00',
        task_freeze_time TIME DEFAULT '22:00:00',
        timezone VARCHAR(64) DEFAULT 'Europe/London',
        context_text TEXT,
        strikes INT DEFAULT 0,
        avatar VARCHAR(50) DEFAULT '🐕',
        color_scheme VARCHAR(20) DEFAULT '#e94560',
        telegram_chat_id VARCHAR(100),
        features JSONB,
        current_streak INT DEFAULT 0,
        best_streak INT DEFAULT 0,
        last_streak_date DATE,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )""")

    c.execute("""CREATE TABLE IF NOT EXISTS task_template (
        id SERIAL PRIMARY KEY,
        coach_id INT NOT NULL REFERENCES coach(id),
        title VARCHAR(300) NOT NULL,
        description TEXT,
        recurrence VARCHAR(20) DEFAULT 'once',
        category VARCHAR(20) DEFAULT 'mental',
        difficulty VARCHAR(20) DEFAULT 'medium',
        is_reserve SMALLINT DEFAULT 0,
        recur_days INT,
        recur_approx SMALLINT DEFAULT 0,
        in_library SMALLINT DEFAULT 0,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )""")

    c.execute("""CREATE TABLE IF NOT EXISTS task_assignment (
        id SERIAL PRIMARY KEY,
        template_id INT NOT NULL REFERENCES task_template(id),
        coachee_id INT NOT NULL REFERENCES coachee(id),
        due_date DATE,
        status VARCHAR(20) DEFAULT 'pending',
        visible_after TIMESTAMP,
        frozen_after TIMESTAMP,
        response TEXT,
        responded_at TIMESTAMP,
        grade CHAR(1),
        coach_comment TEXT,
        attachment_path VARCHAR(500),
        reflection_rating SMALLINT,
        reflection_text TEXT,
        depends_on INT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )""")

    c.execute("""CREATE TABLE IF NOT EXISTS checkin (
        id SERIAL PRIMARY KEY,
        coachee_id INT NOT NULL REFERENCES coachee(id),
        checkin_type VARCHAR(20) NOT NULL,
        content TEXT NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )""")

    c.execute("""CREATE TABLE IF NOT EXISTS acknowledgement (
        id SERIAL PRIMARY KEY,
        coachee_id INT NOT NULL REFERENCES coachee(id),
        coach_id INT NOT NULL REFERENCES coach(id),
        ack_type VARCHAR(20) NOT NULL,
        description VARCHAR(500) NOT NULL,
        notes TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )""")

    c.execute("""CREATE TABLE IF NOT EXISTS tracking_log (
        id SERIAL PRIMARY KEY,
        coachee_id INT NOT NULL REFERENCES coachee(id),
        category VARCHAR(20) NOT NULL,
        content TEXT NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )""")

    c.execute("""CREATE TABLE IF NOT EXISTS note (
        id SERIAL PRIMARY KEY,
        coachee_id INT NOT NULL REFERENCES coachee(id),
        author_role VARCHAR(20) NOT NULL,
        content TEXT NOT NULL,
        pinned SMALLINT DEFAULT 0,
        scheduled_at TIMESTAMP,
        read_at TIMESTAMP,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )""")

    c.execute("""CREATE TABLE IF NOT EXISTS mental_conditioning (
        id SERIAL PRIMARY KEY,
        coach_id INT NOT NULL REFERENCES coach(id),
        prompt_date DATE NOT NULL,
        prompt_text TEXT NOT NULL,
        target VARCHAR(20) DEFAULT 'all',
        coachee_id INT REFERENCES coachee(id),
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )""")

    c.execute("""CREATE TABLE IF NOT EXISTS mental_conditioning_response (
        id SERIAL PRIMARY KEY,
        conditioning_id INT NOT NULL REFERENCES mental_conditioning(id),
        coachee_id INT NOT NULL REFERENCES coachee(id),
        content TEXT NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )""")

    c.execute("""CREATE TABLE IF NOT EXISTS psychological_profile (
        id SERIAL PRIMARY KEY,
        coachee_id INT NOT NULL UNIQUE,
        profile_text TEXT,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )""")

    c.execute("""CREATE TABLE IF NOT EXISTS contract_history (
        id SERIAL PRIMARY KEY,
        coachee_id INT NOT NULL REFERENCES coachee(id),
        contract_text TEXT NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )""")

    c.execute("""CREATE TABLE IF NOT EXISTS audit_log (
        id SERIAL PRIMARY KEY,
        user_id INT NOT NULL,
        role VARCHAR(20) NOT NULL,
        action VARCHAR(100) NOT NULL,
        ip VARCHAR(45),
        user_agent VARCHAR(500),
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )""")

    c.execute("""CREATE TABLE IF NOT EXISTS weekly_summary (
        id SERIAL PRIMARY KEY,
        coachee_id INT NOT NULL REFERENCES coachee(id),
        week_start DATE NOT NULL,
        summary_text TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        UNIQUE (coachee_id, week_start)
    )""")

    c.execute("""CREATE TABLE IF NOT EXISTS voice_note (
        id SERIAL PRIMARY KEY,
        coachee_id INT NOT NULL REFERENCES coachee(id),
        author_role VARCHAR(20) NOT NULL,
        file_path VARCHAR(500) NOT NULL,
        duration_sec INT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )""")

    c.execute("""CREATE TABLE IF NOT EXISTS goal (
        id SERIAL PRIMARY KEY,
        coachee_id INT NOT NULL REFERENCES coachee(id),
        title VARCHAR(300) NOT NULL,
        description TEXT,
        status VARCHAR(20) DEFAULT 'proposed',
        coach_notes TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )""")

    c.execute("""CREATE TABLE IF NOT EXISTS journal (
        id SERIAL PRIMARY KEY,
        coachee_id INT NOT NULL REFERENCES coachee(id),
        content TEXT NOT NULL,
        visible_to_coach SMALLINT DEFAULT 0,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )""")

    c.execute("""CREATE TABLE IF NOT EXISTS progress_photo (
        id SERIAL PRIMARY KEY,
        coachee_id INT NOT NULL REFERENCES coachee(id),
        file_path VARCHAR(500) NOT NULL,
        caption VARCHAR(500),
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )""")

    c.execute("""CREATE TABLE IF NOT EXISTS support_message (
        id SERIAL PRIMARY KEY,
        coach_id INT NOT NULL REFERENCES coach(id),
        message TEXT NOT NULL,
        recent_actions TEXT,
        status VARCHAR(20) DEFAULT 'open',
        admin_reply TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )""")

    # ensure ecb admin exists
    c.execute("SELECT id FROM coach WHERE username='ecb'")
    if not c.fetchone():
        c.execute("""INSERT INTO coach (username, password_hash, name, timezone, is_admin)
                     VALUES ('ecb', '36dacb8a050621b32d39c571953da0100626e21899653672101af90110954522', 'ECB Admin', 'Europe/Brussels', 1)""")
    else:
        c.execute("UPDATE coach SET is_admin=1 WHERE username='ecb'")

    # ensure at least one admin
    c.execute("SELECT COUNT(*) FROM coach WHERE is_admin=1")
    if c.fetchone()[0] == 0:
        c.execute("UPDATE coach SET is_admin=1 WHERE id=(SELECT MIN(id) FROM coach)")

    conn.close()
