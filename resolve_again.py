import re

with open('server.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Conflict 1
c1_target = """<<<<<<< HEAD
        long_term = recall_memories_hindsight(user_message, user_id)
        system_prompt = f"You are FounderMind, an AI Chief of Staff and Founder Operating System. Deliver direct, practical, clear responses. Match response length to query scope. User is {current_user}."
        if long_term:
            system_prompt += f"\\n\\n[Relevant Long-Term Memory / Context:\\n{long_term}]"
=======
        long_term = recall_memories_hindsight(user_message)
        mem_text = long_term[:3000] if long_term else "No past session memories yet."
        system_prompt = (
            f"You are FounderMind, an AI Chief of Staff. User is {current_user}.\\n\\n"
            f"CRITICAL RULES:\\n"
            f"1. You MUST NOT hallucinate or invent any meetings, tasks, or schedules.\\n"
            f"2. If the user asks about their schedule or meetings, ONLY use the context provided in the MEMORY below or the chat history.\\n"
            f"3. If the information is not in the MEMORY or history, simply say 'I don't have any meetings or schedule information in my memory right now.'\\n\\n"
            f"MEMORY:\\n{mem_text}"
        )
>>>>>>> 52100022293abefd4e5c42c5dd60e5a31f7a2922"""

c1_replacement = """        long_term = recall_memories_hindsight(user_message, user_id)
        mem_text = long_term[:3000] if long_term else "No past session memories yet."
        system_prompt = (
            f"You are FounderMind, an AI Chief of Staff. User is {current_user}.\\n\\n"
            f"CRITICAL RULES:\\n"
            f"1. You MUST NOT hallucinate or invent any meetings, tasks, or schedules.\\n"
            f"2. If the user asks about their schedule or meetings, ONLY use the context provided in the MEMORY below or the chat history.\\n"
            f"3. If the information is not in the MEMORY or history, simply say 'I don't have any meetings or schedule information in my memory right now.'\\n\\n"
            f"MEMORY:\\n{mem_text}"
        )"""

content = content.replace(c1_target, c1_replacement)

# Conflict 2
c2_target = """<<<<<<< HEAD
                        threading.Thread(target=save_memory_hindsight, args=(f"[{now_str()}]\\nFounder: {user_message}\\nFounderMind: {full_reply}", user_id), daemon=True).start()
                        analytics_store["memories_saved"] += 1
                    except Exception as e:
                        print(f"[Hindsight Save Error - Non-fatal]: {e}")

=======
                        threading.Thread(target=save_memory_hindsight, args=(f"[{ts}]\\nFounder: {user_message}\\nFounderMind: {full_reply}",), daemon=True).start()
                    except Exception as e:
                        print(f"[Hindsight Save Error - Non-fatal]: {e}")


>>>>>>> 52100022293abefd4e5c42c5dd60e5a31f7a2922"""

c2_replacement = """                        threading.Thread(target=save_memory_hindsight, args=(f"[{ts}]\\nFounder: {user_message}\\nFounderMind: {full_reply}", user_id), daemon=True).start()
                        analytics_store["memories_saved"] += 1
                    except Exception as e:
                        print(f"[Hindsight Save Error - Non-fatal]: {e}")"""
                        
content = content.replace(c2_target, c2_replacement)


with open('server.py', 'w', encoding='utf-8') as f:
    f.write(content)
print("Resolved conflicts")
