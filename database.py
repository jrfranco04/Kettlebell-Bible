import sqlite3
from datetime import date

DB_FILE = 'workouts.db'

def get_db_connection():
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    return conn

def fetch_all_workouts():
    conn = get_db_connection()
    workouts = conn.execute("SELECT * FROM workouts ORDER BY date_created ASC, id ASC").fetchall()
    conn.close()
    # Convert database rows to a list of Python dictionaries
    return [dict(row) for row in workouts]

def add_workouts(workout_data):
    conn = get_db_connection()
    conn.execute("""
    INSERT INTO workouts (title, type, config, rest, rounds, content, date_created)
    VALUES (?,?,?,?,?,?,?)
    """, (
        workout_data['title'],
        workout_data['type'],
        workout_data['config'],
        workout_data['rest'],
        workout_data['rounds'],
        workout_data['content'],
        date.today().isoformat()
    ))
    conn.commit()
    conn.close()

def delete_workout(workout_id):
    conn = get_db_connection()
    conn.execute("DELETE FROM workouts WHERE id = ?", (workout_id,))
    conn.commit()
    conn.close()

def update_workout(id, data):
    conn = get_db_connection()
    conn.execute("""
    UPDATE workouts
    SET title=?, type=?, config=?, rest=?, rounds=?, content=?
    WHERE id=?
    """, (
        data['title'], data['type'], data['config'],
        data['rest'], data['rounds'], data['content'],
        id
    ))
    conn.commit()
    conn.close()