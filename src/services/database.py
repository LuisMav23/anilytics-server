
import os
import psycopg2
from dotenv import load_dotenv


load_dotenv()
def get_db_connection():
    conn = psycopg2.connect(
        host=os.getenv("RDS_PSQL_HOST"), # anilytics-pgsql.c38ygweaynwh.ap-southeast-1.rds.amazonaws.com
        user=os.getenv("RDS_PSQL_USER"), # postgres
        password=os.getenv("RDS_PSQL_PASS"), # LuisMaverick2323_
        dbname=os.getenv("RDS_PSQL_DB"), # anilytics
        port=os.getenv("RDS_PSQL_PORT") # 5432
    )
    return conn

def close_db_connection(conn):
    if conn:
        conn.close()

def get_plant_data_from_db(limit=10):
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM plant_data ORDER BY created_at DESC LIMIT %s;", (limit,))
        rows = cursor.fetchall()
        cursor.close()
        close_db_connection(conn)
        return rows
    except Exception as e:
        conn.rollback()
        close_db_connection(conn)
        return None
    
def insert_plant_data_into_db(data):
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS plant_data (
                id SERIAL PRIMARY KEY, 
                ph FLOAT, 
                tds FLOAT, 
                temperature FLOAT, 
                humidity FLOAT, 
                created_at TIMESTAMP DEFAULT NOW()
            );
        """)
        cursor.execute("""
            INSERT INTO plant_data (
                ph, tds, temperature, humidity
            )
            VALUES (%s, %s, %s, %s);
        """, (
            data['ph'],
            data['tds'],
            data['temperature'],
            data['humidity'],
        ))
        conn.commit()
        cursor.close()
        close_db_connection(conn)
        return True
    except Exception as e:
        conn.rollback()
        close_db_connection(conn)
        return False
    
def get_fish_data_from_db(limit=10):
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM fish_data ORDER BY created_at DESC LIMIT %s;", (limit,))
        rows = cursor.fetchall()
        cursor.close()
        close_db_connection(conn)
        return rows
    except Exception as e:
        conn.rollback()
        close_db_connection(conn)
        return None

def insert_fish_data_into_db(data):
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS fish_data (
                id SERIAL PRIMARY KEY, 
                turbidity FLOAT, 
                waterTemperature FLOAT, 
                ph FLOAT, 
                created_at TIMESTAMP DEFAULT NOW()
            );
        """)
        cursor.execute("""
            INSERT INTO fish_data (
                turbidity, waterTemperature, ph
            ) 
            VALUES (%s, %s, %s);            
        """, (
            data['turbidity'],
            data['waterTemperature'],
            data['ph'],
        ))
        conn.commit()
        cursor.close()
        close_db_connection(conn)
        return True
    except Exception as e:
        conn.rollback()
        close_db_connection(conn)
        return False
