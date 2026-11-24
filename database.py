import os
import re
import sqlite3
from datetime import datetime
from fastapi import HTTPException
from urllib.parse import urlparse, unquote
from dotenv import load_dotenv

load_dotenv()

DB_TYPE = os.getenv("DB_TYPE", "sqlite").lower()
DATABASE_URL = os.getenv("DATABASE_URL")
SQLITE_DB = os.getenv(
    "SQLITE_DB",
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "alwajud.db"),
)


def _mysql_config():
    if DATABASE_URL:
        rest = DATABASE_URL.split("://", 1)[1]
        creds, hostpart = rest.rsplit("@", 1)
        user, password = creds.split(":", 1)
        hostport, database = hostpart.split("/", 1)
        host, _, port = hostport.partition(":")
        return {
            "host": host,
            "port": int(port) if port else 3306,
            "user": unquote(user),
            "password": unquote(password),
            "database": database.split("?")[0],
        }
    return {
        "host": os.getenv("MYSQL_HOST", "localhost"),
        "port": int(os.getenv("MYSQL_PORT", 3306)),
        "user": os.getenv("MYSQL_USER", "root"),
        "password": os.getenv("MYSQL_PASSWORD", ""),
        "database": os.getenv("MYSQL_DATABASE", "alwajud_db"),
    }

# ── MySQL-compatible functions for SQLite ──────────────────────────
def _parse(v):
    if v is None:
        return None
    s = str(v)[:19]
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            pass
    return None

def _month(v):
    d = _parse(v)
    return d.month if d else None

def _year(v):
    d = _parse(v)
    return d.year if d else None

def _curdate():
    return datetime.now().strftime("%Y-%m-%d")

def _date_format(v, fmt):
    d = _parse(v)
    return d.strftime(fmt) if d else None

def _concat(*args):
    return "".join("" if a is None else str(a) for a in args)


def _sqlite_connect():
    conn = sqlite3.connect(SQLITE_DB)
    conn.row_factory = sqlite3.Row
    conn.create_function("MONTH", 1, _month)
    conn.create_function("YEAR", 1, _year)
    conn.create_function("CURDATE", 0, _curdate)
    conn.create_function("DATE_FORMAT", 2, _date_format)
    conn.create_function("CONCAT", -1, _concat)
    return conn


def _sqlite_sql(sql: str) -> str:
    sql = sql.replace("%s", "?")
    sql = sql.replace("INT AUTO_INCREMENT PRIMARY KEY", "INTEGER PRIMARY KEY AUTOINCREMENT")
    sql = re.sub(
        r"DATE_SUB\(\s*CURDATE\(\)\s*,\s*INTERVAL\s+(\d+)\s+MONTH\s*\)",
        lambda m: f"date('now', '-{m.group(1)} months')",
        sql,
        flags=re.IGNORECASE,
    )
    return sql


def query(sql: str, params: tuple = (), fetchone: bool = False):
    try:
        if DB_TYPE == "mysql":
            import mysql.connector
            conn = mysql.connector.connect(**_mysql_config())
            cursor = conn.cursor(dictionary=True)
            cursor.execute(sql, params)
            if sql.strip().upper().startswith("SELECT"):
                result = cursor.fetchone() if fetchone else cursor.fetchall()
            else:
                conn.commit()
                result = None
            cursor.close()
            conn.close()
            return result

        conn = _sqlite_connect()
        cursor = conn.cursor()
        cursor.execute(_sqlite_sql(sql), params)
        if sql.strip().upper().startswith("SELECT"):
            rows = cursor.fetchone() if fetchone else cursor.fetchall()
            if fetchone:
                result = dict(rows) if rows is not None else None
            else:
                result = [dict(r) for r in rows]
        else:
            conn.commit()
            result = None
        cursor.close()
        conn.close()
        return result
    except HTTPException:
        raise
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"{type(e).__name__}: {e}")