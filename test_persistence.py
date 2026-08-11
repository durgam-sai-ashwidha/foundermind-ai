import requests, uuid, time, sys

session = requests.Session()
url_base = 'http://localhost:5000'
time.sleep(2)

print("Logging in...")
res_login = session.post(f'{url_base}/api/login', json={'username': 'founder@startup.com', 'password': 'founder123'})
print('Login status:', res_login.status_code)

if res_login.status_code != 200:
    print("Login failed")
    sys.exit(1)

chat1_id = str(uuid.uuid4())
print(f"--- Chat 1 ({chat1_id}) ---")
res1 = session.post(f'{url_base}/api/chat', json={'message': 'my favourite color is blue', 'session_id': chat1_id, 'stream': False})
data1 = res1.json()
print("AI Reply 1:", data1.get('response'))

time.sleep(3) # Wait for background thread memory saving

chat2_id = str(uuid.uuid4())
print(f"--- Chat 2 ({chat2_id}) ---")
res2 = session.post(f'{url_base}/api/chat', json={'message': 'what is my favourite color?', 'session_id': chat2_id, 'stream': False})
data2 = res2.json()
print("AI Reply 2:", data2.get('response'))

if 'blue' in data2.get('response', '').lower():
    print("SUCCESS: Memory persisted across sessions!")
else:
    print("FAILED: AI forgot the color!")
    sys.exit(1)
