import mysql.connector
from db_config import db_config

try:
    conn = mysql.connector.connect(**db_config)
    print("Connection successful!")
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users")
    users = cursor.fetchall()
    print("Users:", users)
    cursor.close()
    conn.close()
except mysql.connector.Error as err:
    print(f"Error: {err}")