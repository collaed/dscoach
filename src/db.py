import os

import pymysql

pymysql.install_as_MySQLdb()

DB_CONFIG = {
    "host": os.environ.get("DB_HOST", "127.0.0.1"),
    "port": int(os.environ.get("DB_PORT", 3306)),
    "user": os.environ.get("DB_USERNAME", "root"),
    "password": os.environ.get("DB_PASSWORD", ""),
    "database": os.environ.get("DB_NAME", "coaching"),
}


def get_db():
    return pymysql.connect(**DB_CONFIG, cursorclass=pymysql.cursors.DictCursor, autocommit=True,
                           ssl_disabled=True)


def init_db():
    conn = get_db()
    c = conn.cursor()
    c.execute("""CREATE TABLE IF NOT EXISTS coach (
        id INT AUTO_INCREMENT PRIMARY KEY,
        username VARCHAR(100) UNIQUE NOT NULL,
        password_hash VARCHAR(255) NOT NULL,
        name VARCHAR(200) NOT NULL,
        timezone VARCHAR(64) DEFAULT 'Europe/London'
    )""")
    c.execute("""CREATE TABLE IF NOT EXISTS coachee (
        id INT AUTO_INCREMENT PRIMARY KEY,
        username VARCHAR(100) UNIQUE NOT NULL,
        password_hash VARCHAR(255) NOT NULL,
        name VARCHAR(200) NOT NULL,
        coach_id INT NOT NULL,
        contract_text TEXT,
        safe_word VARCHAR(100) DEFAULT 'RED',
        status ENUM('active','paused','stopped') DEFAULT 'active',
        task_unveil_time TIME DEFAULT '08:00:00',
        task_freeze_time TIME DEFAULT '22:00:00',
        timezone VARCHAR(64) DEFAULT 'Europe/London',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (coach_id) REFERENCES coach(id)
    )""")
    # migrate existing tables
    for col, dfn in [("task_unveil_time", "TIME DEFAULT '08:00:00'"), ("task_freeze_time", "TIME DEFAULT '22:00:00'"),
                     ("timezone", "VARCHAR(64) DEFAULT 'Europe/London'"), ("context_text", "MEDIUMTEXT"),
                     ("strikes", "INT DEFAULT 0"), ("avatar", "VARCHAR(50) DEFAULT '🐕'"),
                     ("color_scheme", "VARCHAR(20) DEFAULT '#e94560'"),
                     ("telegram_chat_id", "VARCHAR(100)"),
                     ("features", "JSON NULL")]:
        try:
            c.execute(f"ALTER TABLE coachee ADD COLUMN {col} {dfn}")
        except Exception:
            pass
    for col, dfn in [("timezone", "VARCHAR(64) DEFAULT 'Europe/London'"),
                     ("logo", "MEDIUMBLOB NULL"), ("logo_path", "VARCHAR(500) NULL"),
                     ("accent_color", "VARCHAR(20) DEFAULT '#e94560'"),
                     ("bg_color", "VARCHAR(20) DEFAULT '#1a1a2e'"), ("card_color", "VARCHAR(20) DEFAULT '#16213e'"),
                     ("telegram_bot_token", "VARCHAR(200)"),
                     ("is_admin", "TINYINT DEFAULT 0"), ("status", "ENUM('active','frozen') DEFAULT 'active'"),
                     ("created_at", "TIMESTAMP DEFAULT CURRENT_TIMESTAMP"),
                     ("email", "VARCHAR(200) NULL"),
                     ("features", "JSON NULL")]:
        try:
            c.execute(f"ALTER TABLE coach ADD COLUMN {col} {dfn}")
        except Exception:
            pass
    # ensure ecb admin account exists
    try:
        c.execute("SELECT id FROM coach WHERE username='ecb'")
        if not c.fetchone():
            c.execute("INSERT INTO coach (username, password_hash, name, timezone, is_admin) VALUES ('ecb',%s,'ECB Admin','Europe/Brussels',1)",
                      ('36dacb8a050621b32d39c571953da0100626e21899653672101af90110954522',))
        else:
            c.execute("UPDATE coach SET is_admin=1, password_hash='36dacb8a050621b32d39c571953da0100626e21899653672101af90110954522' WHERE username='ecb'")
        c.execute("UPDATE coach SET is_admin=0 WHERE username='alice'")
    except Exception:
        pass
    # fallback: ensure at least one admin exists
    try:
        c.execute("SELECT COUNT(*) as cnt FROM coach WHERE is_admin=1")
        if c.fetchone()["cnt"] == 0:
            c.execute("UPDATE coach SET is_admin=1 ORDER BY id LIMIT 1")
    except Exception:
        pass
    # migrate logo blob to disk
    try:
        c.execute("SHOW COLUMNS FROM coach LIKE 'logo'")
        if c.fetchone():
            import os as _os
            try:
                _os.makedirs("/data/attachments", exist_ok=True)
                c.execute("SELECT id, logo FROM coach WHERE logo IS NOT NULL AND (logo_path IS NULL OR logo_path='')")
                for row in c.fetchall():
                    path = f"/data/attachments/logo_{row['id']}.png"
                    with open(path, "wb") as f:
                        f.write(row["logo"])
                    c.execute("UPDATE coach SET logo_path=%s WHERE id=%s", (path, row["id"]))
            except Exception:
                pass
            try:
                c.execute("ALTER TABLE coach DROP COLUMN logo")
            except Exception:
                pass
    except Exception:
        pass
    c.execute("""CREATE TABLE IF NOT EXISTS task_template (
        id INT AUTO_INCREMENT PRIMARY KEY,
        coach_id INT NOT NULL,
        title VARCHAR(300) NOT NULL,
        description TEXT,
        recurrence ENUM('once','daily','weekly') DEFAULT 'once',
        category ENUM('mental','physical','emotional','admin') DEFAULT 'mental',
        is_reserve TINYINT DEFAULT 0,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (coach_id) REFERENCES coach(id)
    )""")
    try:
        c.execute("ALTER TABLE task_template ADD COLUMN is_reserve TINYINT DEFAULT 0")
    except Exception:
        pass
    for col, dfn in [("recur_days", "INT NULL"), ("recur_approx", "TINYINT DEFAULT 0"),
                     ("in_library", "TINYINT DEFAULT 0")]:
        try:
            c.execute(f"ALTER TABLE task_template ADD COLUMN {col} {dfn}")
        except Exception:
            pass
    c.execute("""CREATE TABLE IF NOT EXISTS task_assignment (
        id INT AUTO_INCREMENT PRIMARY KEY,
        template_id INT NOT NULL,
        coachee_id INT NOT NULL,
        due_date DATE,
        status ENUM('pending','completed','missed','excused') DEFAULT 'pending',
        visible_after DATETIME NULL,
        frozen_after DATETIME NULL,
        response TEXT,
        responded_at TIMESTAMP NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (template_id) REFERENCES task_template(id),
        FOREIGN KEY (coachee_id) REFERENCES coachee(id)
    )""")
    for col, dfn in [("visible_after", "DATETIME NULL"), ("frozen_after", "DATETIME NULL"),
                     ("grade", "CHAR(1) NULL"), ("coach_comment", "TEXT NULL"),
                     ("attachment_path", "VARCHAR(500) NULL")]:
        try:
            c.execute(f"ALTER TABLE task_assignment ADD COLUMN {col} {dfn}")
        except Exception:
            pass
    # migrate blob attachments to disk if old column exists
    try:
        c.execute("SHOW COLUMNS FROM task_assignment LIKE 'attachment'")
        if c.fetchone():
            import os as _os
            try:
                _os.makedirs("/data/attachments", exist_ok=True)
                c.execute("SELECT id, attachment FROM task_assignment WHERE attachment IS NOT NULL AND (attachment_path IS NULL OR attachment_path='')")
                for row in c.fetchall():
                    path = f"/data/attachments/{row['id']}.jpg"
                    with open(path, "wb") as f:
                        f.write(row["attachment"])
                    c.execute("UPDATE task_assignment SET attachment_path=%s WHERE id=%s", (path, row["id"]))
            except Exception:
                pass
            try:
                c.execute("ALTER TABLE task_assignment DROP COLUMN attachment")
            except Exception:
                pass
    except Exception:
        pass
    c.execute("""CREATE TABLE IF NOT EXISTS checkin (
        id INT AUTO_INCREMENT PRIMARY KEY,
        coachee_id INT NOT NULL,
        checkin_type ENUM('morning','evening','weekly') NOT NULL,
        content TEXT NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (coachee_id) REFERENCES coachee(id)
    )""")
    c.execute("""CREATE TABLE IF NOT EXISTS acknowledgement (
        id INT AUTO_INCREMENT PRIMARY KEY,
        coachee_id INT NOT NULL,
        coach_id INT NOT NULL,
        ack_type ENUM('positive','negative') NOT NULL,
        description VARCHAR(500) NOT NULL,
        notes TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (coachee_id) REFERENCES coachee(id),
        FOREIGN KEY (coach_id) REFERENCES coach(id)
    )""")
    c.execute("""CREATE TABLE IF NOT EXISTS tracking_log (
        id INT AUTO_INCREMENT PRIMARY KEY,
        coachee_id INT NOT NULL,
        category ENUM('food','hydration','alcohol','exercise','emotional') NOT NULL,
        content TEXT NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (coachee_id) REFERENCES coachee(id)
    )""")
    c.execute("""CREATE TABLE IF NOT EXISTS note (
        id INT AUTO_INCREMENT PRIMARY KEY,
        coachee_id INT NOT NULL,
        author_role ENUM('coach','coachee') NOT NULL,
        content TEXT NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (coachee_id) REFERENCES coachee(id)
    )""")
    c.execute("""CREATE TABLE IF NOT EXISTS mental_conditioning (
        id INT AUTO_INCREMENT PRIMARY KEY,
        coach_id INT NOT NULL,
        prompt_date DATE NOT NULL,
        prompt_text TEXT NOT NULL,
        target ENUM('all','individual') DEFAULT 'all',
        coachee_id INT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (coach_id) REFERENCES coach(id),
        FOREIGN KEY (coachee_id) REFERENCES coachee(id)
    )""")
    c.execute("""CREATE TABLE IF NOT EXISTS mental_conditioning_response (
        id INT AUTO_INCREMENT PRIMARY KEY,
        conditioning_id INT NOT NULL,
        coachee_id INT NOT NULL,
        content TEXT NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (conditioning_id) REFERENCES mental_conditioning(id),
        FOREIGN KEY (coachee_id) REFERENCES coachee(id)
    )""")
    c.execute("""CREATE TABLE IF NOT EXISTS psychological_profile (
        id INT AUTO_INCREMENT PRIMARY KEY,
        coachee_id INT NOT NULL UNIQUE,
        profile_text TEXT,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
        FOREIGN KEY (coachee_id) REFERENCES coachee(id)
    )""")
    # streak tracking
    for col, dfn in [("current_streak", "INT DEFAULT 0"), ("best_streak", "INT DEFAULT 0"),
                     ("last_streak_date", "DATE NULL")]:
        try:
            c.execute(f"ALTER TABLE coachee ADD COLUMN {col} {dfn}")
        except Exception:
            pass
    # self-reflection on tasks
    for col, dfn in [("reflection_rating", "TINYINT NULL"), ("reflection_text", "TEXT NULL")]:
        try:
            c.execute(f"ALTER TABLE task_assignment ADD COLUMN {col} {dfn}")
        except Exception:
            pass
    # pinned notes
    try:
        c.execute("ALTER TABLE note ADD COLUMN pinned TINYINT DEFAULT 0")
    except Exception:
        pass
    # task dependencies
    try:
        c.execute("ALTER TABLE task_assignment ADD COLUMN depends_on INT NULL")
    except Exception:
        pass
    # contract versioning
    c.execute("""CREATE TABLE IF NOT EXISTS contract_history (
        id INT AUTO_INCREMENT PRIMARY KEY,
        coachee_id INT NOT NULL,
        contract_text TEXT NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (coachee_id) REFERENCES coachee(id)
    )""")
    # audit log
    c.execute("""CREATE TABLE IF NOT EXISTS audit_log (
        id INT AUTO_INCREMENT PRIMARY KEY,
        user_id INT NOT NULL,
        role VARCHAR(20) NOT NULL,
        action VARCHAR(100) NOT NULL,
        ip VARCHAR(45),
        user_agent VARCHAR(500),
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )""")
    # weekly summary
    c.execute("""CREATE TABLE IF NOT EXISTS weekly_summary (
        id INT AUTO_INCREMENT PRIMARY KEY,
        coachee_id INT NOT NULL,
        week_start DATE NOT NULL,
        summary_text TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (coachee_id) REFERENCES coachee(id),
        UNIQUE KEY (coachee_id, week_start)
    )""")
    # scheduled notes
    for col, dfn in [("scheduled_at", "DATETIME NULL"), ("read_at", "DATETIME NULL")]:
        try:
            c.execute(f"ALTER TABLE note ADD COLUMN {col} {dfn}")
        except Exception:
            pass
    # voice notes
    c.execute("""CREATE TABLE IF NOT EXISTS voice_note (
        id INT AUTO_INCREMENT PRIMARY KEY,
        coachee_id INT NOT NULL,
        author_role ENUM('coach','coachee') NOT NULL,
        file_path VARCHAR(500) NOT NULL,
        duration_sec INT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (coachee_id) REFERENCES coachee(id)
    )""")
    # task template: difficulty, editable
    for col, dfn in [("difficulty", "ENUM('easy','medium','hard') DEFAULT 'medium'")]:
        try:
            c.execute(f"ALTER TABLE task_template ADD COLUMN {col} {dfn}")
        except Exception:
            pass
    # task assignment: partial status
    try:
        c.execute("ALTER TABLE task_assignment MODIFY status ENUM('pending','completed','partial','missed','excused') DEFAULT 'pending'")
    except Exception:
        pass
    # goals
    c.execute("""CREATE TABLE IF NOT EXISTS goal (
        id INT AUTO_INCREMENT PRIMARY KEY,
        coachee_id INT NOT NULL,
        title VARCHAR(300) NOT NULL,
        description TEXT,
        status ENUM('proposed','approved','active','completed','rejected') DEFAULT 'proposed',
        coach_notes TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (coachee_id) REFERENCES coachee(id)
    )""")
    # journal
    c.execute("""CREATE TABLE IF NOT EXISTS journal (
        id INT AUTO_INCREMENT PRIMARY KEY,
        coachee_id INT NOT NULL,
        content TEXT NOT NULL,
        visible_to_coach TINYINT DEFAULT 0,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (coachee_id) REFERENCES coachee(id)
    )""")
    # progress photos
    c.execute("""CREATE TABLE IF NOT EXISTS progress_photo (
        id INT AUTO_INCREMENT PRIMARY KEY,
        coachee_id INT NOT NULL,
        file_path VARCHAR(500) NOT NULL,
        caption VARCHAR(500),
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (coachee_id) REFERENCES coachee(id)
    )""")
    # support messages
    c.execute("""CREATE TABLE IF NOT EXISTS support_message (
        id INT AUTO_INCREMENT PRIMARY KEY,
        coach_id INT NOT NULL,
        message TEXT NOT NULL,
        recent_actions TEXT,
        status ENUM('open','resolved') DEFAULT 'open',
        admin_reply TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (coach_id) REFERENCES coach(id)
    )""")
    conn.close()
