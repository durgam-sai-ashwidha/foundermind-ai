import re

with open('server.py', 'r', encoding='utf-8') as f:
    content = f.read()

# 1. Update the existing session deletion endpoint to include hindsight sync
session_delete_old = """@app.route("/chat/sessions/<session_id>", methods=["DELETE"])
@login_required
def delete_chat_session(session_id):
    try:
        with get_db_connection() as conn:
            conn.execute("DELETE FROM chat_messages WHERE session_id = ? AND user_id = ?", (session_id, session["user_id"]))
            conn.execute("DELETE FROM chat_sessions WHERE id = ? AND user_id = ?", (session_id, session["user_id"]))
            conn.commit()
        return jsonify({"status": "deleted", "id": session_id})
    except Exception as e:
        return jsonify({"error": str(e)}), 500"""

session_delete_new = """@app.route("/chat/sessions/<session_id>", methods=["DELETE"])
@app.route("/api/chat/session/<session_id>", methods=["DELETE"])
@login_required
def delete_chat_session(session_id):
    try:
        with get_db_connection() as conn:
            conn.execute("DELETE FROM chat_messages WHERE session_id = ? AND user_id = ?", (session_id, session["user_id"]))
            conn.execute("DELETE FROM chat_sessions WHERE id = ? AND user_id = ?", (session_id, session["user_id"]))
            conn.commit()
            
        threading.Thread(
            target=save_memory_hindsight, 
            args=(f"[DELETED SESSION]\\nThe user completely deleted the chat session (ID: {session_id}). Any specific requests or context from that session should be disregarded.", session["user_id"]), 
            daemon=True
        ).start()
            
        return jsonify({"status": "deleted", "id": session_id})
    except Exception as e:
        return jsonify({"error": str(e)}), 500"""

content = content.replace(session_delete_old, session_delete_new)


# 2. Add the PUT /api/chat/<id> and DELETE /api/chat/<id> endpoints
endpoints_code = """
@app.route("/api/chat/<int:msg_id>", methods=["PUT"])
@login_required
def update_chat_message(msg_id):
    data = request.json
    new_message = data.get("message")
    if not new_message:
        return jsonify({"error": "Message content required"}), 400
        
    try:
        with get_db_connection() as conn:
            c = conn.cursor()
            c.execute("SELECT message FROM chat_messages WHERE id = ? AND user_id = ?", (msg_id, session["user_id"]))
            row = c.fetchone()
            if not row:
                return jsonify({"error": "Message not found"}), 404
            
            old_message = row["message"]
            conn.execute("UPDATE chat_messages SET message = ? WHERE id = ? AND user_id = ?", (new_message, msg_id, session["user_id"]))
            conn.commit()
            
        threading.Thread(
            target=save_memory_hindsight, 
            args=(f"[CORRECTION/EDIT]\\nThe user corrected a previous statement.\\nOld statement: {old_message}\\nNew statement: {new_message}", session["user_id"]), 
            daemon=True
        ).start()
            
        return jsonify({"status": "updated", "id": msg_id, "message": new_message})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/chat/<int:msg_id>", methods=["DELETE"])
@login_required
def delete_chat_message(msg_id):
    try:
        with get_db_connection() as conn:
            c = conn.cursor()
            c.execute("SELECT message FROM chat_messages WHERE id = ? AND user_id = ?", (msg_id, session["user_id"]))
            row = c.fetchone()
            if not row:
                return jsonify({"error": "Message not found"}), 404
                
            old_message = row["message"]
            conn.execute("DELETE FROM chat_messages WHERE id = ? AND user_id = ?", (msg_id, session["user_id"]))
            conn.commit()
            
        threading.Thread(
            target=save_memory_hindsight, 
            args=(f"[DELETED]\\nThe user deleted the following statement. Disregard it: {old_message}", session["user_id"]), 
            daemon=True
        ).start()
            
        return jsonify({"status": "deleted", "id": msg_id})
    except Exception as e:
        return jsonify({"error": str(e)}), 500
"""

# Insert these endpoints right before @app.route("/chat/history", methods=["GET"])
target = """@app.route("/chat/history", methods=["GET"])"""
if target in content and "def update_chat_message" not in content:
    content = content.replace(target, endpoints_code + "\n" + target)

with open('server.py', 'w', encoding='utf-8') as f:
    f.write(content)
print("Added endpoints to server.py")
