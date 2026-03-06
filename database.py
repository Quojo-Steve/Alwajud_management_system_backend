import mysql.connector
from mysql.connector import Error
from fastapi import HTTPException

def query(sql: str, params: tuple = (), fetchone: bool = False):
    try:
        conn = mysql.connector.connect(
            host="localhost",
            user="root",
            password="SuzzyA-2",
            database="alwajud_db"
        )
        cursor = conn.cursor(dictionary=True)
        cursor.execute(sql, params)

        # Only fetch results for SELECT queries
        if sql.strip().upper().startswith("SELECT"):
            result = cursor.fetchone() if fetchone else cursor.fetchall()
        else:
            conn.commit()
            result = None

        cursor.close()
        conn.close()
        return result
    except Error as e:
        raise HTTPException(status_code=500, detail=str(e))

