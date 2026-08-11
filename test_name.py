import requests, uuid, time, sqlite3

session = requests.Session()
url_base = 'http://localhost:5000'
time.sleep(2)

res_login = session.post(f'{url_base}/api/login', json={'username': 'founder@startup.com', 'password': 'founder123'})
print('Login:', res_login.status_code)

chat_session_id = str(uuid.uuid4())
res = session.post(f'{url_base}/api/chat', json={'message': 'change my name to Sirish', 'session_id': chat_session_id})
data = res.json()
print('Response JSON:', data.get('updated_user'))
print('LLM Response:', data.get('response'))

conn = sqlite3.connect('foundermind.db')
c = conn.cursor()
c.execute("SELECT username FROM users WHERE email='founder@startup.com'")
print('DB Username:', c.fetchone()[0])
