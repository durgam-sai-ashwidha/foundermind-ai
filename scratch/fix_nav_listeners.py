import re

with open(r'C:\Users\priya\.gemini\antigravity\scratch\foundermind-ai\index.html', 'r', encoding='utf-8') as f:
    content = f.read()

# 1. Update showPage function in JS to support clean hash navigation and alias mapping
old_show_page = """function showPage(name,el){
  document.querySelectorAll('.page').forEach(p=>p.classList.remove('active'));
  document.querySelectorAll('.nav-item').forEach(n=>n.classList.remove('active'));
  const target = document.getElementById('page-'+name);
  if(target) target.classList.add('active');
  if(el)el.classList.add('active');
  
  if(name==='analytics'){
    updateAnalytics();
    if(!analyticsPollTimer){
      analyticsPollTimer = setInterval(updateAnalytics, 4000);
    }
  } else {
    if(analyticsPollTimer){
      clearInterval(analyticsPollTimer);
      analyticsPollTimer = null;
    }
  }
  if(name==='overview')updateOverview();
}"""

new_show_page = """function showPage(name, el){
  if (!name) return;
  // Normalize alias tab names
  let normalized = name.toLowerCase();
  if (normalized === 'calendar') normalized = 'meetings';
  if (normalized === 'projects') normalized = 'tasks';
  if (normalized === 'people') normalized = 'documents';
  if (normalized === 'insights') normalized = 'analytics';

  // Update Page visibility
  document.querySelectorAll('.page').forEach(p => p.classList.remove('active'));
  const target = document.getElementById('page-' + normalized);
  if (target) {
    target.classList.add('active');
  }

  // Update Nav Item active state
  document.querySelectorAll('.nav-sidebar .nav-item').forEach(n => n.classList.remove('active'));
  if (el && el.classList && el.classList.contains('nav-item')) {
    el.classList.add('active');
  } else {
    const navMatch = document.querySelector(`.nav-sidebar .nav-item[onclick*="'${name}'"]`) || 
                     document.querySelector(`.nav-sidebar .nav-item[onclick*="'${normalized}'"]`);
    if (navMatch) navMatch.classList.add('active');
  }

  // Update URL Hash cleanly
  try {
    if (window.location.hash !== '#' + normalized) {
      history.replaceState(null, '', '#' + normalized);
    }
  } catch(e) {}

  // Section-specific triggers
  if (normalized === 'analytics') {
    updateAnalytics();
    if (!analyticsPollTimer) {
      analyticsPollTimer = setInterval(updateAnalytics, 4000);
    }
  } else {
    if (analyticsPollTimer) {
      clearInterval(analyticsPollTimer);
      analyticsPollTimer = null;
    }
  }
  if (normalized === 'overview') updateOverview();
}

// Hash change navigation listener
window.addEventListener('hashchange', function() {
  const hash = window.location.hash.replace('#', '');
  if (hash) showPage(hash);
});"""

content = content.replace(old_show_page, new_show_page)

# 2. Add Global Cmd+K / Ctrl+K and Global Search handler
old_keydown = """document.addEventListener('keydown', function(e){
  if(e.ctrlKey||e.metaKey||e.altKey) return;               // let shortcuts through"""

new_keydown = """document.addEventListener('keydown', function(e){
  // ===== ⌘K / Ctrl+K GLOBAL SEARCH SHORTCUT =====
  if ((e.metaKey || e.ctrlKey) && (e.key === 'k' || e.key === 'K')) {
    e.preventDefault();
    const searchInput = document.getElementById('globalSearchInput') || document.querySelector('.top-search-input');
    if (searchInput) {
      searchInput.focus();
      searchInput.select();
      showToast('🔍 Global search activated. Type to filter company items.', 'info', '⌘K');
    }
    return;
  }

  if(e.ctrlKey||e.metaKey||e.altKey) return;               // let shortcuts through"""

content = content.replace(old_keydown, new_keydown)

# Add handleGlobalSearch function right after showPage
global_search_js = """
// ===== GLOBAL SEARCH FILTER =====
function handleGlobalSearch(query) {
  if (!query) return;
  const q = query.trim().toLowerCase();
  if (!q) return;

  // Filter tasks if visible or on tasks page
  const taskCards = document.querySelectorAll('#taskList .task-item, .task-card');
  let taskMatches = 0;
  taskCards.forEach(card => {
    const text = card.textContent.toLowerCase();
    if (text.includes(q)) {
      card.style.display = '';
      taskMatches++;
    } else {
      card.style.display = 'none';
    }
  });

  // Filter memories if visible
  const memoryCards = document.querySelectorAll('#memoryList .memory-card, .memory-item');
  let memoryMatches = 0;
  memoryCards.forEach(card => {
    const text = card.textContent.toLowerCase();
    if (text.includes(q)) {
      card.style.display = '';
      memoryMatches++;
    } else {
      card.style.display = 'none';
    }
  });

  // Filter documents if visible
  const docCards = document.querySelectorAll('#docList .doc-card, .doc-item');
  let docMatches = 0;
  docCards.forEach(card => {
    const text = card.textContent.toLowerCase();
    if (text.includes(q)) {
      card.style.display = '';
      docMatches++;
    } else {
      card.style.display = 'none';
    }
  });
}
"""

content = content.replace(new_show_page, new_show_page + "\n" + global_search_js)

# 3. Ensure handleLogout clears local storage and redirects cleanly
old_logout = """async function handleLogout() {
  try {
    await fetch('/api/logout', { method: 'POST', credentials: 'include' });
    checkAuthState();
  } catch (e) {
    checkAuthState();
  }
}"""

new_logout = """async function handleLogout() {
  try {
    await fetch('/api/logout', { method: 'POST', credentials: 'include' });
  } catch (e) {
    console.error('Logout API call error:', e);
  }
  localStorage.removeItem('username');
  localStorage.removeItem('session_id');
  localStorage.removeItem('user');
  checkAuthState();
  showToast('Logged out successfully', 'info', '👋');
}"""

content = content.replace(old_logout, new_logout)

# Write updated content
with open(r'C:\Users\priya\.gemini\antigravity\scratch\foundermind-ai\index.html', 'w', encoding='utf-8') as f:
    f.write(content)

print("Nav, Search, and Logout event listeners updated in index.html!")
