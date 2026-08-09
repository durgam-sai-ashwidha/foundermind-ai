import os, sys, json, urllib.request, http.cookiejar
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

BASE = 'http://127.0.0.1:5000'
cj = http.cookiejar.CookieJar()
opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))

def req(method, path, data=None):
    url = BASE + path
    body = json.dumps(data).encode() if data else None
    r = urllib.request.Request(url, data=body, headers={'Content-Type':'application/json'}, method=method)
    try:
        res = opener.open(r, timeout=20)
        return res.getcode(), json.loads(res.read().decode())
    except urllib.error.HTTPError as e:
        try: return e.code, json.loads(e.read().decode())
        except: return e.code, {}
    except Exception as e:
        return 0, {'error': str(e)}

passed = 0
TICK = "[PASS]"
CROSS = "[FAIL]"

print("=" * 65)
print("  FounderMind AI -- 8/8 Automated Verification")
print("=" * 65)

# CHECK 1: Health
s, d = req('GET', '/health')
ok = s == 200 and d.get('status') in ('ok', 'healthy')
passed += ok
print(f"  CHECK 1/8  GET /health .............. {TICK if ok else CROSS} {s} status={d.get('status')}")

# CHECK 2: Login
s, d = req('POST', '/api/login', {'username': 'founder@startup.com', 'password': 'founder123'})
ok = s == 200 and d.get('authenticated') is True
passed += ok
print(f"  CHECK 2/8  POST /api/login .......... {TICK if ok else CROSS} {s} auth={d.get('authenticated')}")

# CHECK 3: /api/me
s, d = req('GET', '/api/me')
ok = s == 200 and d.get('authenticated') is True
passed += ok
print(f"  CHECK 3/8  GET /api/me .............. {TICK if ok else CROSS} {s} auth={d.get('authenticated')}")

# CHECK 4: Tasks route aliases
s1, t1 = req('GET', '/tasks')
s2, t2 = req('GET', '/api/tasks')
ok = s1 == 200 and s2 == 200 and isinstance(t1, list) and isinstance(t2, list)
passed += ok
count = len(t1) if isinstance(t1, list) else '?'
print(f"  CHECK 4/8  GET /tasks+/api/tasks .... {TICK if ok else CROSS} {s1}/{s2} ({count} tasks)")

# CHECK 5: Create task
s, d = req('POST', '/api/tasks', {'text': 'Q3 Investor Pitch Deck', 'priority': 'high'})
ok = s in (200, 201) and bool(d.get('id'))
passed += ok
tid = str(d.get('id', ''))[:8]
print(f"  CHECK 5/8  POST /api/tasks .......... {TICK if ok else CROSS} {s} id={tid}")

# CHECK 6: Create meeting
s, d = req('POST', '/api/meetings', {'title': 'Series A Sync', 'date': '2026-08-20', 'time': '10:00 AM', 'with_': 'Roelof Botha'})
ok = s in (200, 201) and bool(d.get('id'))
passed += ok
mid = str(d.get('id', ''))[:8]
print(f"  CHECK 6/8  POST /api/meetings ....... {TICK if ok else CROSS} {s} id={mid}")

# CHECK 7: Analytics
s, d = req('GET', '/api/analytics')
ok = s == 200 and 'budget_used' in d
passed += ok
print(f"  CHECK 7/8  GET /api/analytics ....... {TICK if ok else CROSS} {s} budget_used={d.get('budget_used')}")

# CHECK 8: AI Chat
s, d = req('POST', '/api/chat', {'message': 'Hello FounderMind, summarize my high priority tasks.'})
reply = d.get('reply') or d.get('response') or ''
ok = s == 200 and bool(reply)
passed += ok
print(f"  CHECK 8/8  POST /api/chat ........... {TICK if ok else CROSS} {s} reply_len={len(reply)}")

print("=" * 65)
print(f"  RESULT: {passed}/8 CHECKS PASSED")
print("=" * 65)
sys.exit(0 if passed == 8 else 1)
