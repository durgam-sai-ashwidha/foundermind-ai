import re

with open('server.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Conflict 1
c1_target = """<<<<<<< HEAD
        pw_hash = hash_password("founder123")
        c.execute("INSERT OR IGNORE INTO users (username, email, password_hash) VALUES (?, ?, ?)", ("founder", "founder@startup.com", pw_hash))
=======
        c.execute("SELECT id FROM users WHERE LOWER(email) = 'founder@startup.com'")
        if not c.fetchone():
            pw_hash = hash_password("founder123")
            c.execute("INSERT INTO users (username, email, password_hash) VALUES (?, ?, ?)", ("founder", "founder@startup.com", pw_hash))
>>>>>>> d38cce1 (fix: update sidebar profileAvatar badge and profileName dynamically on chat name change)"""

c1_replacement = """        c.execute("SELECT id FROM users WHERE LOWER(email) = 'founder@startup.com'")
        if not c.fetchone():
            pw_hash = hash_password("founder123")
            c.execute("INSERT OR IGNORE INTO users (username, email, password_hash) VALUES (?, ?, ?)", ("founder", "founder@startup.com", pw_hash))"""

content = content.replace(c1_target, c1_replacement)


# Conflict 2
c2_target = """<<<<<<< HEAD
=======
        mem_text = long_term_memories[:3000] if long_term_memories else "No past session memories needed for simple queries."
>>>>>>> d38cce1 (fix: update sidebar profileAvatar badge and profileName dynamically on chat name change)"""
c2_replacement = """"""
content = content.replace(c2_target, c2_replacement)

# Conflict 3
c3_target = """<<<<<<< HEAD
        
        # Fetch conversation history from DB
        history_msgs = []
        try:
            with get_db_connection() as conn:
                c = conn.cursor()
                c.execute("SELECT role, message FROM chat_messages WHERE session_id = ? ORDER BY timestamp DESC LIMIT 6", (chat_session_id,))
                for row in reversed(c.fetchall()):
                    history_msgs.append({"role": row["role"], "content": row["message"]})
        except Exception as e:
            print(f"[History fetch error]: {e}")
            
        mem_text = long_term[:3000] if long_term else "No past session memories yet."
        system_prompt = f"You are FounderMind, an AI Chief of Staff. User is {current_user}.\\n\\nMEMORY:\\n{mem_text}"
        
        messages = [{"role": "system", "content": system_prompt}]
        messages.extend(history_msgs)
        messages.append({"role": "user", "content": user_message})
=======
        system_prompt = f"You are FounderMind, an AI Chief of Staff and Founder Operating System. Deliver direct, practical, clear responses. Match response length to query scope. User is {current_user}."
        if long_term:
            system_prompt += f"\\n\\n[Relevant Long-Term Memory / Context:\\n{long_term}]"
>>>>>>> d38cce1 (fix: update sidebar profileAvatar badge and profileName dynamically on chat name change)"""
c3_replacement = """        system_prompt = f"You are FounderMind, an AI Chief of Staff and Founder Operating System. Deliver direct, practical, clear responses. Match response length to query scope. User is {current_user}."
        if long_term:
            system_prompt += f"\\n\\n[Relevant Long-Term Memory / Context:\\n{long_term}]"
        
        msgs = [{"role": "system", "content": system_prompt}] + history_messages + [{"role": "user", "content": user_message}]"""
content = content.replace(c3_target, c3_replacement)

# Conflict 4
c4_target = """<<<<<<< HEAD
                    messages=messages,
=======
                    messages=msgs,
>>>>>>> d38cce1 (fix: update sidebar profileAvatar badge and profileName dynamically on chat name change)"""
c4_replacement = """                    messages=msgs,"""
content = content.replace(c4_target, c4_replacement)


with open('server.py', 'w', encoding='utf-8') as f:
    f.write(content)
print("Resolved conflicts")
