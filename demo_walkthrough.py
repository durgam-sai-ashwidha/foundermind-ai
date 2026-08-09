import os
import sys
import json
import urllib.request
import urllib.parse
import http.cookiejar

sys.stdout.reconfigure(encoding='utf-8', errors='replace')

BASE_URL = os.getenv("BASE_URL", "http://127.0.0.1:5000")

# Setup CookieJar for session persistence across requests
cj = http.cookiejar.CookieJar()
opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))

def make_request(method, path, data=None):
    url = f"{BASE_URL}{path}"
    headers = {'Content-Type': 'application/json'}
    body = json.dumps(data).encode('utf-8') if data is not None else None
    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        res = opener.open(req)
        status = res.getcode()
        resp_data = json.loads(res.read().decode('utf-8'))
        return status, resp_data
    except urllib.error.HTTPError as e:
        status = e.code
        try:
            resp_data = json.loads(e.read().decode('utf-8'))
        except Exception:
            resp_data = {"error": e.reason}
        return status, resp_data
    except Exception as e:
        return 500, {"error": str(e)}

def main():
    print("=" * 70)
    print(" 🚀 FounderMind AI -- Automated 8/8 System Walkthrough & Verification")
    print("=" * 70)

    passed_checks = 0

    # CHECK 1: Health Check
    status, data = make_request("GET", "/health")
    if status == 200 and data.get("status") in ("ok", "healthy"):
        print(f" [CHECK 1/8] GET  /health ............................ ✅ 200 OK (Status: {data.get('status')})")
        passed_checks += 1
    else:
        print(f" [CHECK 1/8] GET  /health ............................ ❌ {status} (Expected 200)")

    # CHECK 2: User Authentication Login
    status, data = make_request("POST", "/api/login", {"username": "founder@startup.com", "password": "founder123"})
    if status == 200 and data.get("authenticated") is True:
        print(f" [CHECK 2/8] POST /api/login ......................... ✅ 200 OK (User: {data.get('user', {}).get('username')})")
        passed_checks += 1
    else:
        print(f" [CHECK 2/8] POST /api/login ................. me ..... ❌ {status} {data}")

    # CHECK 3: Session State Verification
    status, data = make_request("GET", "/api/me")
    if status == 200 and data.get("authenticated") is True:
        print(f" [CHECK 3/8] GET  /api/me ............................ ✅ 200 OK (Authenticated: True)")
        passed_checks += 1
    else:
        print(f" [CHECK 3/8] GET  /api/me ............................ ❌ {status} {data}")

    # CHECK 4: Task Route Alias Verification GET /tasks and /api/tasks
    status1, tasks1 = make_request("GET", "/tasks")
    status2, tasks2 = make_request("GET", "/api/tasks")
    if status1 == 200 and status2 == 200 and isinstance(tasks1, list) and isinstance(tasks2, list):
        print(f" [CHECK 4/8] GET  /tasks & /api/tasks ................ ✅ 200 OK (Returned {len(tasks1)} tasks)")
        passed_checks += 1
    else:
        print(f" [CHECK 4/8] GET  /tasks & /api/tasks ................ ❌ Status: {status1}/{status2}")

    # CHECK 5: Task Creation POST /api/tasks
    status, task = make_request("POST", "/api/tasks", {"text": "Complete Q3 Investor Pitch Deck", "priority": "high"})
    if status in (200, 201) and task.get("id"):
        print(f" [CHECK 5/8] POST /api/tasks ......................... ✅ {status} Created (Task ID: {task.get('id')[:8]}...)")
        passed_checks += 1
    else:
        print(f" [CHECK 5/8] POST /api/tasks ......................... ❌ {status} {task}")

    # CHECK 6: Meeting Scheduling POST /api/meetings
    status, meeting = make_request("POST", "/api/meetings", {"title": "Series A Sync with Sequoia", "date": "2026-08-20", "time": "10:00 AM", "with_": "Roelof Botha"})
    if status in (200, 201) and meeting.get("id"):
        print(f" [CHECK 6/8] POST /api/meetings ...................... ✅ {status} Created (Meeting: {meeting.get('title')})")
        passed_checks += 1
    else:
        print(f" [CHECK 6/8] POST /api/meetings ...................... ❌ {status} {meeting}")

    # CHECK 7: Telemetry & Analytics GET /api/analytics
    status, analytics = make_request("GET", "/api/analytics")
    if status == 200 and "budget_used" in analytics:
        print(f" [CHECK 7/8] GET  /api/analytics ..................... ✅ 200 OK (Budget Spent: ${analytics.get('budget_used', 0.0):.6f})")
        passed_checks += 1
    else:
        print(f" [CHECK 7/8] GET  /api/analytics ..................... ❌ {status} {analytics}")

    # CHECK 8: Cascadeflow AI Chat POST /api/chat
    status, chat_resp = make_request("POST", "/api/chat", {"message": "Hello FounderMind, summarize my high priority tasks."})
    reply_text = chat_resp.get("reply") or chat_resp.get("response") or ""
    if status == 200 and reply_text:
        print(f" [CHECK 8/8] POST /api/chat .......................... ✅ 200 OK (Reply Len: {len(reply_text)} chars)")
        passed_checks += 1
    else:
        print(f" [CHECK 8/8] POST /api/chat .......................... ❌ {status} {chat_resp}")

    print("=" * 70)
    print(f" VERIFICATION RESULTS: {passed_checks}/8 CHECKS PASSED")
    print("=" * 70)

    sys.exit(0 if passed_checks == 8 else 1)

if __name__ == "__main__":
    main()
