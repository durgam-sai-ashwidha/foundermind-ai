import sqlite3
conn = sqlite3.connect("foundermind.db")
c = conn.cursor()
c.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='users';")
res = c.fetchone()
print(res[0] if res else "No users table found")
