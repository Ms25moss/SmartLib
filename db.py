import os
import mysql.connector
from mysql.connector import Error

def get_db_connection():
    try:
        connection = mysql.connector.connect(
            host=os.environ.get("DB_HOST"),
            user=os.environ.get("DB_USER"),
            password=os.environ.get("DB_PASSWORD"),
            database=os.environ.get("DB_NAME", "smartlib_db"),
            port=int(os.environ.get("DB_PORT", "4000")),
            ssl_ca=os.path.join(
                os.path.dirname(__file__),
                "isrgrootx1.pem"
            ),
            ssl_verify_cert=True,
            ssl_verify_identity=True
        )

        if connection.is_connected():
            print("SmartLib online database connected successfully!")
            return connection

    except Error as e:
        print("Database connection error:", e)

    return None