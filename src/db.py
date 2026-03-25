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
    return pymysql.connect(**DB_CONFIG, cursorclass=pymysql.cursors.DictCursor, autocommit=True)


def init_db():
    conn = get_db()
    c = conn.cursor()
    c.execute("""CREATE TABLE IF NOT EXISTS coach (
        id INT AUTO_INCREMENT PRIMARY KEY,
        username VARCHAR(100) UNIQUE NOT NULL,
        password_hash VARCHAR(255) NOT NULL,
        name VARCHAR(200) NOT NULL
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
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (coach_id) REFERENCES coach(id)
    )""")
    c.execute("""CREATE TABLE IF NOT EXISTS task_template (
        id INT AUTO_INCREMENT PRIMARY KEY,
        coach_id INT NOT NULL,
        title VARCHAR(300) NOT NULL,
        description TEXT,
        recurrence ENUM('once','daily','weekly') DEFAULT 'once',
        category ENUM('mental','physical','emotional','admin') DEFAULT 'mental',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (coach_id) REFERENCES coach(id)
    )""")
    c.execute("""CREATE TABLE IF NOT EXISTS task_assignment (
        id INT AUTO_INCREMENT PRIMARY KEY,
        template_id INT NOT NULL,
        coachee_id INT NOT NULL,
        due_date DATE,
        status ENUM('pending','completed','missed','excused') DEFAULT 'pending',
        response TEXT,
        responded_at TIMESTAMP NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (template_id) REFERENCES task_template(id),
        FOREIGN KEY (coachee_id) REFERENCES coachee(id)
    )""")
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
    conn.close()
