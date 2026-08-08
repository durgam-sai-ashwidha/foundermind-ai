import sys, json, os, sqlite3

sys.stdout.reconfigure(encoding='utf-8', errors='replace')

DB_PATH = os.path.join(os.getcwd(), 'foundermind.db')

# ── STEP 1: First 'server start' — seed data ────────────────────────────────
print('=' * 60)
print('STEP 1: Simulating first server start -- seeding data...')
print('=' * 60)

import server
client = server.app.test_client()

# Add a task
r = client.post('/tasks', json={'text': 'Close seed round at 3M', 'priority': 'high'})
task = r.get_json(); task_id = task['id']
print(f"  [ADD TASK]     {r.status_code} -> id={task_id[:8]}... text='{task['text']}'")

# Add a meeting
r = client.post('/meetings', json={
    'title': 'Sequoia Partner Meeting',
    'date': '2026-08-15',
    'time': '2:00 PM',
    'with_': 'Roelof Botha'
})
meeting = r.get_json(); meeting_id = meeting['id']
print(f"  [ADD MEETING]  {r.status_code} -> id={meeting_id[:8]}... title='{meeting['title']}'")

# Add a document
r = client.post('/documents', json={'name': 'Pitch Deck v4.pptx', 'type': 'Pitch Deck'})
doc = r.get_json(); doc_id = doc['id']
print(f"  [ADD DOCUMENT] {r.status_code} -> id={doc_id[:8]}... name='{doc['name']}'")

# Verify counts via /health
r = client.get('/health')
h = r.get_json()
print(f"  [HEALTH]       tasks={h['tasks']}, meetings={h['meetings']}, documents={h['documents']}")

# ── STEP 2: Read directly from SQLite (bypass all Python in-memory state) ─────
print()
print('=' * 60)
print('STEP 2: Simulating server restart -- reading raw SQLite file directly...')
print('=' * 60)

conn = sqlite3.connect(DB_PATH)
conn.row_factory = sqlite3.Row

tasks_db    = [dict(r) for r in conn.execute('SELECT * FROM tasks').fetchall()]
meetings_db = [dict(r) for r in conn.execute('SELECT * FROM meetings').fetchall()]
docs_db     = [dict(r) for r in conn.execute('SELECT * FROM documents').fetchall()]
audit_db    = [dict(r) for r in conn.execute('SELECT * FROM audit_logs ORDER BY id DESC LIMIT 5').fetchall()]
conn.close()

print(f"  [TASKS in DB]     {len(tasks_db)} row(s)")
for t in tasks_db:
    print(f"    - [{t['priority'].upper()}] {t['text']}  (done={t['done']})")

print(f"  [MEETINGS in DB]  {len(meetings_db)} row(s)")
for m in meetings_db:
    print(f"    - {m['title']} on {m['date']} with {m['with_']}")

print(f"  [DOCUMENTS in DB] {len(docs_db)} row(s)")
for d in docs_db:
    print(f"    - {d['name']} ({d['type']})")

print(f"  [AUDIT LOGS]      {len(audit_db)} recent entries")
for a in audit_db:
    print(f"    [{a['timestamp']}] {a['event']}")

# ── STEP 3: Re-import server (fresh module — same as restart) ─────────────────
print()
print('=' * 60)
print('STEP 3: Verifying via fresh Flask client (simulated restart)...')
print('=' * 60)

if 'server' in sys.modules:
    del sys.modules['server']
import server as server2
client2 = server2.app.test_client()

tasks_after   = client2.get('/tasks').get_json()
meetings_after = client2.get('/meetings').get_json()
docs_after    = client2.get('/documents').get_json()

print(f"  [/tasks]     -> {len(tasks_after)} task(s) returned after restart")
for t in tasks_after:
    print(f"    - [{t['priority'].upper()}] {t['text']}")

print(f"  [/meetings]  -> {len(meetings_after)} meeting(s) returned after restart")
for m in meetings_after:
    print(f"    - {m['title']} on {m['date']}")

print(f"  [/documents] -> {len(docs_after)} document(s) returned after restart")
for d in docs_after:
    print(f"    - {d['name']}")

# ── STEP 4: PATCH task (mark done) and DELETE document — verify in SQLite ────
print()
print('=' * 60)
print('STEP 4: PATCH task (mark done), DELETE document -- verify in SQLite...')
print('=' * 60)

patch_r = client2.patch(f'/tasks/{task_id}', json={'done': True})
print(f"  [PATCH /tasks/{task_id[:8]}...] {patch_r.status_code} -> done={patch_r.get_json()['done']}")

del_r = client2.delete(f'/documents/{doc_id}')
print(f"  [DEL /documents/{doc_id[:8]}...]  {del_r.status_code} -> {del_r.get_json()}")

# Verify direct SQLite state
conn = sqlite3.connect(DB_PATH)
conn.row_factory = sqlite3.Row
task_row = conn.execute('SELECT done FROM tasks WHERE id=?', (task_id,)).fetchone()
doc_row  = conn.execute('SELECT id FROM documents WHERE id=?', (doc_id,)).fetchone()
conn.close()

task_done_ok  = bool(task_row['done']) == True
doc_deleted_ok = doc_row is None

print(f"  [SQLite] task.done={bool(task_row['done'])} (expected True) -> {'PASS' if task_done_ok else 'FAIL'}")
print(f"  [SQLite] doc deleted={doc_row is None} (expected True)       -> {'PASS' if doc_deleted_ok else 'FAIL'}")

# ── RESULT ────────────────────────────────────────────────────────────────────
print()
print('=' * 60)
all_passed = (
    len(tasks_db) >= 1
    and len(meetings_db) >= 1
    and len(docs_db) >= 1
    and len(tasks_after) >= 1
    and len(meetings_after) >= 1
    and task_done_ok
    and doc_deleted_ok
)
status = "ALL PASSED" if all_passed else "SOME FAILED"
print(f"SQLITE PERSISTENCE TEST: {status}")
print('=' * 60)
sys.exit(0 if all_passed else 1)
