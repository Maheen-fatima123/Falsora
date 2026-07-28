import psycopg2

def get_connection():
    conn = psycopg2.connect(
        host="localhost",
        database="falsora_db",
        user="postgres",
        password="1234"   # your actual postgres password
    )
    return conn

if __name__ == "__main__":
    conn = get_connection()
    print("Connected successfully!")
    conn.close()