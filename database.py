import os
import re
import sqlite3

from fastapi import HTTPException


DB_TYPE = os.getenv("DB_TYPE", "sqlite").lower()
SQLITE_DB = os.getenv("SQLITE_DB", "alwajud.db")


def _sqlite_sql(sql: str) -> str:
    sql = sql.replace("%s", "?")
    sql = sql.replace("INT AUTO_INCREMENT PRIMARY KEY", "INTEGER PRIMARY KEY AUTOINCREMENT")
    sql = re.sub(r"CURDATE\(\)", "date('now')", sql, flags=re.IGNORECASE)
    sql = re.sub(r"\bMONTH\(([^)]+)\)", r"CAST(strftime('%m', \1) AS INTEGER)", sql, flags=re.IGNORECASE)
    sql = re.sub(r"\bYEAR\(([^)]+)\)", r"CAST(strftime('%Y', \1) AS INTEGER)", sql, flags=re.IGNORECASE)
    sql = re.sub(
        r"DATE_FORMAT\(([^,]+),\s*'([^']+)'\)",
        lambda match: f"strftime('{match.group(2)}', {match.group(1).strip()})",
        sql,
        flags=re.IGNORECASE,
    )
    sql = re.sub(
        r"DATE_SUB\(CURDATE\(\),\s*INTERVAL\s+(\d+)\s+MONTH\)",
        lambda match: f"date('now', '-{match.group(1)} months')",
        sql,
        flags=re.IGNORECASE,
    )
    return sql


def query(sql: str, params: tuple = (), fetchone: bool = False):
    try:
        if DB_TYPE == "mysql":
            import mysql.connector

            conn = mysql.connector.connect(
                host=os.getenv("MYSQL_HOST", "localhost"),
                user=os.getenv("MYSQL_USER", "root"),
                password=os.getenv("MYSQL_PASSWORD", ""),
                database=os.getenv("MYSQL_DATABASE", "alwajud_db"),
            )
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

        conn = sqlite3.connect(SQLITE_DB)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute(_sqlite_sql(sql), params)
        if sql.strip().upper().startswith("SELECT"):
            rows = cursor.fetchone() if fetchone else cursor.fetchall()
            if fetchone:
                result = dict(rows) if rows is not None else None
            else:
                result = [dict(row) for row in rows]
        else:
            conn.commit()
            result = None
        cursor.close()
        conn.close()
        return result
    except sqlite3.Error as e:
        raise HTTPException(status_code=500, detail=str(e))
