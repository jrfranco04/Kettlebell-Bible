import sqlite3
import json
import os
from datetime import date

# Connect the database (build the file if it doesn't exist)
conn = sqlite3.connect('workouts.db')
cursor = conn.cursor()

# Create the table - This defines the headers for the columns
cursor.execute("""
    CREATE TABLE IF NOT EXISTS workouts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT NOT NULL,
        type TEXT,
        config TEXT,
        rest TEXT,
        rounds TEXT,
        content TEXT,
        date_created TEXT
    )
""")

# Migrates existing JSON data
json_file = "workouts.json"

if os.path.exists(json_file):
    print(f'Found {json_file}. Migrating data...')
    with open(json_file, 'r') as f:
        data = json.load(f)

    # Today's date for migration
    today = date.today().isoformat()

    count = 0
    for workout in data:
        # Insert each workout into the database
        cursor.execute("""
            INSERT INTO workouts (title, type, config, rest, rounds, content, date_created)
            VALUES (?,?,?,?,?,?,?)
        """, (
            workout.get('title'),
            workout.get('type'),
            workout.get('config'),
            workout.get('rest'),
            workout.get('rounds'),
            workout.get('content'),
            today
        ))
        count += 1
    print(f'Successfully migrated {count} workouts to SQL')
else:
    print('No JSON file found. Created an empty database.')

# Save and close
conn.commit()
conn.close()
print('Database setup complete: workouts.db created.')