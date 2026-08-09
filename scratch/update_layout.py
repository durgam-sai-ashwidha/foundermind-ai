import re

with open(r'C:\Users\priya\.gemini\antigravity\scratch\foundermind-ai\index.html', 'r', encoding='utf-8') as f:
    content = f.read()

# 1. Update CSS styles for gold accent, nav badges, top bar, sidebar, and footer
additional_css = """
/* ENHANCED SIDEBAR & LAYOUT STYLES */
.nav-item.active {
  background: rgba(229, 169, 60, 0.15) !important;
  color: #E5A93C !important;
  border-left-color: #DAA520 !important;
  font-weight: 700 !important;
}
.nav-item:hover {
  background: rgba(229, 169, 60, 0.08);
  color: #f5c842;
}
.nav-badge {
  margin-left: auto;
  background: rgba(229, 169, 60, 0.18);
  color: #E5A93C;
  border: 1px solid rgba(229, 169, 60, 0.35);
  border-radius: 10px;
  padding: 1px 7px;
  font-size: 0.65rem;
  font-weight: 700;
  font-family: monospace;
}
.quick-action-btn:hover {
  background: linear-gradient(135deg, #f5c842, #E5A93C) !important;
  transform: translateY(-1px);
  box-shadow: 0 4px 12px rgba(229, 169, 60, 0.4) !important;
}
.activity-scroll-row::-webkit-scrollbar {
  display: none;
}
.activity-pill:hover {
  border-color: #E5A93C !important;
  background: rgba(229, 169, 60, 0.06) !important;
}
"""

# Insert additional CSS right before </style>
content = content.replace("</style>", additional_css + "\n</style>", 1)

# 2. Extract base64 logo src from current header if exists
logo_src_match = re.search(r'<img class="logo-brain" src="([^"]+)"', content)
logo_src = logo_src_match.group(1) if logo_src_match else ""

# 3. Construct New Header HTML
new_header_html = f"""<!-- HEADER -->
<header style="display: flex; align-items: center; justify-content: space-between; padding: 10px 24px; background: var(--surface); border-bottom: 1px solid var(--border); flex-shrink: 0; gap: 20px; z-index: 10;">
  <!-- Logo -->
  <div class="logo" style="display: flex; align-items: center; gap: 11px; flex-shrink: 0;">
    <img class="logo-brain" src="{logo_src}" style="width:36px;height:36px;border-radius:50%;object-fit:cover;filter:drop-shadow(0 0 6px rgba(229,169,60,0.5));">
    <div>
      <div class="logo-text" style="font-family:Georgia,serif;font-weight:900;font-size:1.2rem;background:linear-gradient(90deg,#d4a017,#f5c842,#fef3c7);-webkit-background-clip:text;-webkit-text-fill-color:transparent;background-clip:text;">FounderMind</div>
      <div class="logo-sub" style="font-size:0.58rem;color:var(--muted);letter-spacing:0.12em;text-transform:uppercase;font-family:monospace;">AI Chief of Staff</div>
    </div>
  </div>

  <!-- Center Search Bar -->
  <div class="top-search-wrap" style="flex: 1; max-width: 480px; position: relative; display: flex; align-items: center;">
    <span style="position: absolute; left: 14px; color: var(--muted); font-size: 0.85rem;">🔍</span>
    <input type="text" class="top-search-input" placeholder="Search anything in your company..." style="width: 100%; background: var(--card); border: 1px solid var(--border); border-radius: 20px; padding: 8px 45px 8px 38px; color: var(--text); font-size: 0.8rem; outline: none; transition: border-color 0.2s;" onfocus="this.style.borderColor='#E5A93C'" onblur="this.style.borderColor='var(--border)'">
    <span class="cmd-k-badge" style="position: absolute; right: 12px; background: var(--border); color: var(--muted); border-radius: 4px; padding: 2px 7px; font-size: 0.65rem; font-family: monospace; font-weight: 700;">⌘K</span>
  </div>

  <!-- Right Actions & Utilities -->
  <div class="header-right" style="display: flex; align-items: center; gap: 14px; flex-shrink: 0;">
    <button class="quick-action-btn" onclick="showToast('⚡ Quick Action: Create Task, Log Memory, or Start Meeting','info','⚡')" style="background: linear-gradient(135deg, #E5A93C, #DAA520); color: #000; border: none; border-radius: 8px; padding: 8px 16px; font-size: 0.8rem; font-weight: 800; cursor: pointer; display: flex; align-items: center; gap: 6px; box-shadow: 0 2px 10px rgba(229,169,60,0.35); transition: all 0.2s;">
      ⚡ + Quick Action
    </button>
    
    <div class="header-icon-btn" style="position: relative; cursor: pointer; font-size: 1.1rem; padding: 6px; color: var(--text);" title="Notifications" onclick="showToast('3 new notifications available','info','🔔')">
      🔔
      <span class="notif-badge" style="position: absolute; top: 1px; right: 1px; background: #ef4444; color: #fff; font-size: 0.6rem; font-weight: 700; border-radius: 50%; width: 16px; height: 16px; display: flex; align-items: center; justify-content: center;">3</span>
    </div>

    <div class="header-icon-btn" style="cursor: pointer; font-size: 1.1rem; padding: 6px; color: var(--text);" title="Inbox" onclick="showToast('Inbox synced with primary email','info','📥')">
      📥
    </div>

    <div class="status-pill"><div class="status-dot"></div>🟢 Online &amp; Remembering</div>
  </div>
</header>"""

# Replace Header
header_pattern = r'<!-- HEADER -->.*?<!-- FOUNDER METRICS BAR -->'
content = re.sub(header_pattern, new_header_html + "\n\n<!-- FOUNDER METRICS BAR -->", content, flags=re.DOTALL)

# 4. Construct New Nav Sidebar HTML
nav_brain_match = re.search(r'<img class="nav-brain" src="([^"]+)"', content)
nav_brain_src = nav_brain_match.group(1) if nav_brain_match else logo_src

new_sidebar_html = f"""<!-- NAV SIDEBAR -->
  <div class="nav-sidebar">
    <div class="nav-logo-area" style="padding: 14px 16px; display: flex; align-items: center; gap: 10px; border-bottom: 1px solid var(--border);">
      <img class="nav-brain" src="{nav_brain_src}" style="width:32px;height:32px;border-radius:50%;object-fit:cover;filter:drop-shadow(0 0 6px rgba(229,169,60,0.4));">
      <div>
        <div style="font-family:Georgia,serif;font-weight:900;font-size:0.95rem;color:var(--text)">FounderMind</div>
        <div style="font-size:0.55rem;color:#E5A93C;letter-spacing:0.12em;text-transform:uppercase;font-family:monospace">WORKSPACE</div>
      </div>
    </div>

    <div style="flex: 1; overflow-y: auto;">
      <!-- MAIN -->
      <div class="nav-section-title">MAIN</div>
      <div class="nav-item active" onclick="showPage('overview',this)"><span class="nav-icon">🏠</span> Overview</div>
      <div class="nav-item" onclick="showPage('chat',this)"><span class="nav-icon">💬</span> Ask FounderMind</div>
      <div class="session-section" style="padding: 2px 8px 4px;">
        <div class="new-chat-btn" id="newChatBtn" onclick="newChat()">＋ New Chat</div>
        <div class="session-list" id="sessionList"></div>
      </div>

      <!-- WORK -->
      <div class="nav-section-title">WORK</div>
      <div class="nav-item" onclick="showPage('tasks',this)"><span class="nav-icon">✅</span> Tasks <span class="nav-badge">12</span></div>
      <div class="nav-item" onclick="showPage('meetings',this)"><span class="nav-icon">📅</span> Calendar <span class="nav-badge" style="background:rgba(59,130,246,0.15);color:#3b82f6;border-color:rgba(59,130,246,0.3)">6</span></div>
      <div class="nav-item" onclick="showPage('meetings',this)"><span class="nav-icon">🤝</span> Meetings</div>
      <div class="nav-item" onclick="showPage('tasks',this)"><span class="nav-icon">📁</span> Projects</div>

      <!-- COMPANY BRAIN -->
      <div class="nav-section-title">COMPANY BRAIN</div>
      <div class="nav-item" onclick="showPage('memory',this)"><span class="nav-icon">🧠</span> Memory</div>
      <div class="nav-item" onclick="showPage('documents',this)"><span class="nav-icon">📄</span> Documents</div>
      <div class="nav-item" onclick="showPage('documents',this)"><span class="nav-icon">👥</span> People</div>

      <!-- INSIGHTS -->
      <div class="nav-section-title">INSIGHTS</div>
      <div class="nav-item" onclick="showPage('analytics',this)"><span class="nav-icon">📊</span> Founder Insights</div>

      <!-- SETTINGS -->
      <div class="nav-section-title">SETTINGS</div>
      <div class="nav-item" onclick="showPage('settings',this)"><span class="nav-icon">⚙️</span> Settings</div>
    </div>

    <!-- PROFILE CARD -->
    <div class="profile-chip" style="cursor: pointer; display: flex; align-items: center; justify-content: space-between; padding: 12px 14px; border-top: 1px solid var(--border); background: var(--card);">
      <div style="display: flex; align-items: center; gap: 10px; overflow: hidden;" onclick="showPage('settings',document.querySelector('[onclick*=settings]'))">
        <div class="profile-avatar" id="profileAvatar" style="background: linear-gradient(135deg, #E5A93C, #DAA520); width: 34px; height: 34px; border-radius: 50%; display: flex; align-items: center; justify-content: center; font-size: 0.85rem; font-weight: 800; color: #000; flex-shrink: 0;">A</div>
        <div style="overflow: hidden;">
          <div class="profile-name" id="profileName" style="font-size: 0.8rem; font-weight: 700; color: var(--text); white-space: nowrap; overflow: hidden; text-overflow: ellipsis;">Ash</div>
          <div class="profile-role" style="font-size: 0.62rem; color: #E5A93C; font-family: monospace;">Founder &amp; CEO</div>
        </div>
      </div>
      <div style="display: flex; align-items: center; gap: 6px;">
        <span title="Toggle Theme" onclick="toggleTheme()" style="cursor:pointer;font-size:0.85rem;padding:4px;border-radius:4px;background:rgba(255,255,255,0.06);">🌙</span>
        <span title="Help" onclick="showToast('FounderMind Support: help@foundermind.ai','info','❓')" style="cursor:pointer;font-size:0.85rem;padding:4px;border-radius:4px;background:rgba(255,255,255,0.06);">❓</span>
        <span title="Logout" onclick="handleLogout()" style="cursor:pointer;font-size:0.85rem;padding:4px;border-radius:4px;background:rgba(255,255,255,0.06);">🚪</span>
      </div>
    </div>
  </div>"""

sidebar_pattern = r'<!-- NAV SIDEBAR -->.*?<div class="page-area">'
content = re.sub(sidebar_pattern, new_sidebar_html + "\n\n  <!-- PAGE AREA -->\n  <div class=\"page-area\">", content, flags=re.DOTALL)

# 5. Construct Recent Activity Footer HTML
footer_html = """
<!-- BOTTOM RECENT ACTIVITY FOOTER -->
<footer class="activity-footer" style="background: var(--surface); border-top: 1px solid var(--border); padding: 8px 18px; flex-shrink: 0; display: flex; align-items: center; gap: 14px; overflow: hidden; z-index: 10;">
  <div style="font-size: 0.72rem; font-weight: 800; color: #DAA520; text-transform: uppercase; letter-spacing: 0.08em; white-space: nowrap; display: flex; align-items: center; gap: 6px; flex-shrink: 0;">
    <span>⚡</span> Recent Activity:
  </div>
  <div class="activity-scroll-row" style="display: flex; align-items: center; gap: 10px; overflow-x: auto; flex: 1; scrollbar-width: none; padding-bottom: 2px;">
    
    <!-- Activity Pill 1 -->
    <div class="activity-pill" style="display: flex; align-items: center; gap: 8px; background: var(--card); border: 1px solid var(--border); border-radius: 20px; padding: 5px 12px; font-size: 0.74rem; white-space: nowrap; flex-shrink: 0; cursor: pointer; transition: all 0.15s;">
      <span style="background: rgba(34,197,94,0.18); color: #22c55e; width: 20px; height: 20px; border-radius: 50%; display: flex; align-items: center; justify-content: center; font-size: 0.7rem; font-weight: bold;">✓</span>
      <span><strong>Sirish completed API integration</strong> <span style="color: var(--muted); font-size: 0.68rem;">- 2h ago • <span style="color: #22c55e;">Engineering</span></span></span>
    </div>

    <!-- Activity Pill 2 -->
    <div class="activity-pill" style="display: flex; align-items: center; gap: 8px; background: var(--card); border: 1px solid var(--border); border-radius: 20px; padding: 5px 12px; font-size: 0.74rem; white-space: nowrap; flex-shrink: 0; cursor: pointer; transition: all 0.15s;">
      <span style="background: rgba(168,85,247,0.18); color: #a855f7; width: 20px; height: 20px; border-radius: 50%; display: flex; align-items: center; justify-content: center; font-size: 0.7rem; font-weight: bold;">👥</span>
      <span><strong>Ananya updated campaign plan</strong> <span style="color: var(--muted); font-size: 0.68rem;">- 4h ago • <span style="color: #a855f7;">Marketing</span></span></span>
    </div>

    <!-- Activity Pill 3 -->
    <div class="activity-pill" style="display: flex; align-items: center; gap: 8px; background: var(--card); border: 1px solid var(--border); border-radius: 20px; padding: 5px 12px; font-size: 0.74rem; white-space: nowrap; flex-shrink: 0; cursor: pointer; transition: all 0.15s;">
      <span style="background: rgba(234,179,8,0.18); color: #eab308; width: 20px; height: 20px; border-radius: 50%; display: flex; align-items: center; justify-content: center; font-size: 0.7rem; font-weight: bold;">📄</span>
      <span><strong>Investor deck v2 uploaded</strong> <span style="color: var(--muted); font-size: 0.68rem;">- Yesterday • <span style="color: #eab308;">Documents</span></span></span>
    </div>

    <!-- Activity Pill 4 -->
    <div class="activity-pill" style="display: flex; align-items: center; gap: 8px; background: var(--card); border: 1px solid var(--border); border-radius: 20px; padding: 5px 12px; font-size: 0.74rem; white-space: nowrap; flex-shrink: 0; cursor: pointer; transition: all 0.15s;">
      <span style="background: rgba(236,72,153,0.18); color: #ec4899; width: 20px; height: 20px; border-radius: 50%; display: flex; align-items: center; justify-content: center; font-size: 0.7rem; font-weight: bold;">🧠</span>
      <span><strong>New decision recorded</strong> <span style="color: var(--muted); font-size: 0.68rem;">- Yesterday • <span style="color: #ec4899;">Decision Journal</span></span></span>
    </div>

  </div>
</footer>
"""

# Place footer right before </body>
content = content.replace("</body>", footer_html + "\n</body>")

with open(r'C:\Users\priya\.gemini\antigravity\scratch\foundermind-ai\index.html', 'w', encoding='utf-8') as f:
    f.write(content)

print("Successfully updated index.html!")
