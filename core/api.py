"""
REST API Server — control and monitor JARVIS via HTTP.
"""
import threading
import json
from typing import Optional, TYPE_CHECKING
from flask import Flask, request, jsonify, render_template_string
from flask_cors import CORS

from core.config import config, JarvisConfig
from core.brain import JarvisBrain
from core.voice import VoiceEngine
from core.tasks import TaskManager
from core.notifier import notify

if TYPE_CHECKING:
    import jarvis as jarvis_main


app = Flask(__name__)
CORS(app)

# Global references (set by main)
jarvis_instance: Optional["jarvis_main.Jarvis"] = None
voice_engine: Optional[VoiceEngine] = None
brain: Optional[JarvisBrain] = None
task_manager: Optional[TaskManager] = None


def require_auth(f):
    """Decorator to require API authentication."""
    def wrapped(*args, **kwargs):
        cfg = config.get()
        if cfg.api.auth_token:
            token = request.headers.get('Authorization', '').replace('Bearer ', '')
            if token != cfg.api.auth_token:
                return jsonify({"error": "Unauthorized"}), 401
        return f(*args, **kwargs)
    wrapped.__name__ = f.__name__
    return wrapped


@app.route('/')
def dashboard():
    """Serve the web dashboard."""
    return render_template_string(DASHBOARD_HTML)


@app.route('/api/status')
@require_auth
def api_status():
    """Get JARVIS status."""
    if not jarvis_instance:
        return jsonify({"error": "JARVIS not running"}), 503
    
    # Lazy import to avoid circular dependency
    import jarvis as jarvis_main
    
    modules_status = {}
    for name, mod in jarvis_main.modules.items():
        modules_status[name] = {
            "loaded": mod is not None,
            "summary": mod.get_summary() if mod and hasattr(mod, 'get_summary') else "N/A"
        }
    
    return jsonify({
        "running": jarvis_instance.running,
        "voice_language": voice_engine.last_language if voice_engine else "unknown",
        "modules": modules_status,
        "tasks": {
            "pending": len(task_manager.get_pending()) if task_manager else 0,
            "overdue": len(task_manager.get_overdue()) if task_manager else 0,
        },
        "uptime": "N/A"  # Could add start time tracking
    })


@app.route('/api/command', methods=['POST'])
@require_auth
def api_command():
    """Send a command to JARVIS."""
    if not jarvis_instance:
        return jsonify({"error": "JARVIS not running"}), 503
    
    data = request.get_json()
    if not data or 'command' not in data:
        return jsonify({"error": "Missing 'command' field"}), 400
    
    command = data['command']
    # Process in background to avoid blocking
    threading.Thread(target=jarvis_instance.handle_command, args=(command,), daemon=True).start()
    
    return jsonify({"status": "accepted", "command": command})


@app.route('/api/speak', methods=['POST'])
@require_auth
def api_speak():
    """Make JARVIS speak."""
    if not voice_engine:
        return jsonify({"error": "Voice engine not available"}), 503
    
    data = request.get_json()
    if not data or 'text' not in data:
        return jsonify({"error": "Missing 'text' field"}), 400
    
    text = data['text']
    language = data.get('language')
    threading.Thread(target=voice_engine.speak, args=(text, language), daemon=True).start()
    
    return jsonify({"status": "speaking", "text": text})


@app.route('/api/tasks', methods=['GET', 'POST'])
@require_auth
def api_tasks():
    """Manage tasks."""
    if not task_manager:
        return jsonify({"error": "Task manager not available"}), 503
    
    if request.method == 'GET':
        return jsonify({
            "pending": task_manager.get_pending(),
            "overdue": task_manager.get_overdue(),
            "all": task_manager.tasks
        })
    
    data = request.get_json()
    if not data or 'title' not in data:
        return jsonify({"error": "Missing 'title' field"}), 400
    
    task = task_manager.add_task(
        title=data['title'],
        deadline=data.get('deadline'),
        category=data.get('category', 'general')
    )
    return jsonify({"status": "created", "task": task})


@app.route('/api/tasks/<int:task_id>/complete', methods=['POST'])
@require_auth
def api_complete_task(task_id):
    """Mark a task as complete."""
    if not task_manager:
        return jsonify({"error": "Task manager not available"}), 503
    
    task = task_manager.complete_task(task_id)
    if task:
        return jsonify({"status": "completed", "task": task})
    return jsonify({"error": "Task not found"}), 404


@app.route('/api/modules/<module_name>/check', methods=['POST'])
@require_auth
def api_check_module(module_name):
    """Trigger a manual check for a module."""
    if not jarvis_instance:
        return jsonify({"error": "JARVIS not running"}), 503
    
    check_methods = {
        'email': jarvis_instance._check_emails,
        'whatsapp': jarvis_instance._check_whatsapp,
        'instagram': jarvis_instance._check_instagram,
        'telegram': jarvis_instance._check_telegram,
        'calendar': jarvis_instance._check_calendar,
        'tasks': jarvis_instance._check_tasks,
        'jobs': jarvis_instance._search_jobs_background,
    }
    
    if module_name not in check_methods:
        return jsonify({"error": f"Unknown module: {module_name}"}), 404
    
    announce = request.get_json().get('announce', True) if request.get_json() else True
    threading.Thread(target=check_methods[module_name], args=(announce,), daemon=True).start()
    
    return jsonify({"status": "checking", "module": module_name})


@app.route('/api/config', methods=['GET', 'PUT'])
@require_auth
def api_config():
    """Get or update configuration."""
    cfg = config.get()
    
    if request.method == 'GET':
        # Return safe config (no secrets)
        safe = {
            "voice": cfg.voice.__dict__,
            "scheduler": cfg.scheduler.__dict__,
            "notifications": cfg.notifications.__dict__,
            "api": {k: v for k, v in cfg.api.__dict__.items() if k != 'auth_token'},
            "briefing": cfg.briefing.__dict__,
            "auto_start": cfg.auto_start.__dict__,
            "modules": {k: v.__dict__ for k, v in cfg.modules.items()},
        }
        return jsonify(safe)
    
    data = request.get_json()
    if not data:
        return jsonify({"error": "Invalid JSON"}), 400
    
    # Update allowed config paths
    allowed_paths = [
        'voice.wake_word', 'voice.tts_provider', 'voice.default_language',
        'scheduler.enabled', 'scheduler.intervals',
        'notifications.enabled', 'notifications.windows_toast', 'notifications.sound_alerts',
        'briefing.enabled', 'briefing.morning_time', 'briefing.evening_time', 'briefing.include',
        'auto_start.enabled', 'auto_start.method',
    ]
    
    for path in allowed_paths:
        if path in data:
            config.update(path, data[path])
    
    config.save()
    return jsonify({"status": "updated"})


@app.route('/api/shutdown', methods=['POST'])
@require_auth
def api_shutdown():
    """Shutdown JARVIS."""
    if jarvis_instance:
        threading.Thread(target=jarvis_instance.shutdown, daemon=True).start()
        return jsonify({"status": "shutting down"})
    return jsonify({"error": "JARVIS not running"}), 503


@app.route('/api/briefing', methods=['POST'])
@require_auth
def api_briefing():
    """Trigger a manual briefing."""
    if not jarvis_instance:
        return jsonify({"error": "JARVIS not running"}), 503
    
    briefing_type = request.get_json().get('type', 'full') if request.get_json() else 'full'
    threading.Thread(target=jarvis_instance._give_status_report, daemon=True).start()
    
    return jsonify({"status": "briefing started", "type": briefing_type})


# Dashboard HTML
DASHBOARD_HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>JARVIS Dashboard</title>
    <style>
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: #0d1117; color: #c9d1d9; min-height: 100vh; }
        .header { background: #161b22; border-bottom: 1px solid #30363d; padding: 1rem 2rem; display: flex; justify-content: space-between; align-items: center; }
        .header h1 { color: #58a6ff; font-size: 1.5rem; }
        .status-badge { padding: 0.25rem 0.75rem; border-radius: 9999px; font-size: 0.875rem; font-weight: 600; }
        .status-online { background: #238636; color: white; }
        .status-offline { background: #da3633; color: white; }
        .container { max-width: 1400px; margin: 0 auto; padding: 2rem; }
        .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(350px, 1fr)); gap: 1.5rem; }
        .card { background: #161b22; border: 1px solid #30363d; border-radius: 8px; padding: 1.5rem; }
        .card h2 { color: #58a6ff; margin-bottom: 1rem; font-size: 1.1rem; display: flex; align-items: center; gap: 0.5rem; }
        .card h2::before { content: ''; width: 8px; height: 8px; background: #58a6ff; border-radius: 50%; }
        .module-list { display: flex; flex-direction: column; gap: 0.75rem; }
        .module-item { display: flex; justify-content: space-between; align-items: center; padding: 0.75rem; background: #0d1117; border-radius: 6px; border: 1px solid #30363d; }
        .module-info { display: flex; flex-direction: column; gap: 0.25rem; }
        .module-name { font-weight: 600; }
        .module-summary { font-size: 0.8rem; color: #8b949e; }
        .module-status { width: 10px; height: 10px; border-radius: 50%; }
        .status-loaded { background: #238636; }
        .status-unloaded { background: #da3633; }
        .task-list { display: flex; flex-direction: column; gap: 0.5rem; }
        .task-item { padding: 0.75rem; background: #0d1117; border-radius: 6px; border: 1px solid #30363d; display: flex; justify-content: space-between; align-items: center; }
        .task-title { font-weight: 500; }
        .task-meta { font-size: 0.8rem; color: #8b949e; }
        .task-overdue { border-left: 3px solid #da3633; }
        .task-pending { border-left: 3px solid #d29922; }
        .btn { padding: 0.5rem 1rem; border: none; border-radius: 6px; font-weight: 600; cursor: pointer; transition: all 0.2s; }
        .btn-primary { background: #238636; color: white; }
        .btn-primary:hover { background: #2ea043; }
        .btn-secondary { background: #30363d; color: #c9d1d9; border: 1px solid #484f58; }
        .btn-secondary:hover { background: #484f58; }
        .btn-danger { background: #da3633; color: white; }
        .btn-danger:hover { background: #f85149; }
        .command-input { display: flex; gap: 0.5rem; margin-top: 1rem; }
        .command-input input { flex: 1; padding: 0.75rem; background: #0d1117; border: 1px solid #30363d; border-radius: 6px; color: #c9d1d9; font-size: 1rem; }
        .command-input input:focus { outline: none; border-color: #58a6ff; }
        .log-area { height: 200px; overflow-y: auto; background: #0d1117; border: 1px solid #30363d; border-radius: 6px; padding: 1rem; font-family: monospace; font-size: 0.85rem; line-height: 1.6; }
        .log-entry { margin-bottom: 0.25rem; }
        .log-time { color: #8b949e; }
        .log-command { color: #58a6ff; }
        .log-response { color: #7ee787; }
        .tabs { display: flex; gap: 0.5rem; margin-bottom: 1rem; border-bottom: 1px solid #30363d; padding-bottom: 0.5rem; }
        .tab { padding: 0.5rem 1rem; background: none; border: none; color: #8b949e; cursor: pointer; font-size: 0.9rem; border-radius: 6px 6px 0 0; }
        .tab.active { color: #58a6ff; background: #161b22; border: 1px solid #30363d; border-bottom: none; }
        .tab-panel { display: none; }
        .tab-panel.active { display: block; }
        .config-section { display: flex; flex-direction: column; gap: 1rem; }
        .config-item { display: flex; justify-content: space-between; align-items: center; padding: 0.75rem; background: #0d1117; border-radius: 6px; border: 1px solid #30363d; }
        .config-label { font-weight: 500; }
        .config-value { color: #8b949e; font-family: monospace; font-size: 0.85rem; }
        .toggle { width: 44px; height: 24px; background: #30363d; border-radius: 12px; position: relative; cursor: pointer; border: 1px solid #484f58; }
        .toggle.active { background: #238636; }
        .toggle::after { content: ''; position: absolute; width: 18px; height: 18px; background: white; border-radius: 50%; top: 2px; left: 2px; transition: left 0.2s; }
        .toggle.active::after { left: 24px; }
    </style>
</head>
<body>
    <header class="header">
        <h1>🤖 JARVIS Dashboard</h1>
        <span id="statusBadge" class="status-badge status-offline">OFFLINE</span>
    </header>
    <div class="container">
        <div class="grid">
            <div class="card">
                <h2>System Status</h2>
                <div class="module-list" id="modulesList">
                    <div class="module-item">
                        <div class="module-info">
                            <span class="module-name">Loading...</span>
                        </div>
                    </div>
                </div>
            </div>
            <div class="card">
                <h2>Tasks</h2>
                <div class="task-list" id="tasksList">
                    <div class="task-item"><span class="task-title">Loading...</span></div>
                </div>
            </div>
            <div class="card">
                <h2>Voice Command</h2>
                <div class="command-input">
                    <input type="text" id="commandInput" placeholder="Type a command (e.g., 'check email', 'add task buy groceries by tomorrow')..." onkeypress="if(event.key==='Enter') sendCommand()">
                    <button class="btn btn-primary" onclick="sendCommand()">Send</button>
                </div>
                <div style="margin-top: 1rem;">
                    <button class="btn btn-secondary" onclick="triggerBriefing('full')">Full Briefing</button>
                    <button class="btn btn-secondary" onclick="triggerBriefing('morning')">Morning Briefing</button>
                    <button class="btn btn-secondary" onclick="triggerBriefing('evening')">Evening Briefing</button>
                </div>
            </div>
            <div class="card">
                <h2>Activity Log</h2>
                <div class="log-area" id="logArea">
                    <div class="log-entry"><span class="log-time">[--:--:--]</span> <span class="log-response">Dashboard loaded. Waiting for JARVIS...</span></div>
                </div>
            </div>
        </div>
        
        <div class="card" style="margin-top: 1.5rem;">
            <div class="tabs">
                <button class="tab active" onclick="showTab('modules')">Modules</button>
                <button class="tab" onclick="showTab('config')">Configuration</button>
                <button class="tab" onclick="showTab('api')">API Docs</button>
            </div>
            <div id="tab-modules" class="tab-panel active">
                <div class="module-list" id="allModulesList"></div>
            </div>
            <div id="tab-config" class="tab-panel">
                <div class="config-section" id="configSection"></div>
            </div>
            <div id="tab-api" class="tab-panel">
                <pre style="background: #0d1117; padding: 1rem; border-radius: 6px; border: 1px solid #30363d; overflow-x: auto; font-size: 0.85rem;">
GET    /api/status              - Get system status
POST   /api/command             - Send command { "command": "..." }
POST   /api/speak               - Make JARVIS speak { "text": "...", "language": "hi" }
GET    /api/tasks               - List all tasks
POST   /api/tasks               - Create task { "title": "...", "deadline": "2024-12-31" }
POST   /api/tasks/:id/complete  - Complete task
POST   /api/modules/:name/check - Trigger module check
GET    /api/config              - Get configuration
PUT    /api/config              - Update configuration
POST   /api/briefing            - Trigger briefing { "type": "full|morning|evening" }
POST   /api/shutdown            - Shutdown JARVIS
                </pre>
            </div>
        </div>
    </div>

    <script>
        const API_BASE = '';
        let authToken = '';
        
        // Check for auth token in localStorage
        if (localStorage.getItem('jarvis_auth_token')) {
            authToken = localStorage.getItem('jarvis_auth_token');
        }
        
        function log(type, message) {
            const area = document.getElementById('logArea');
            const time = new Date().toLocaleTimeString();
            const entry = document.createElement('div');
            entry.className = 'log-entry';
            entry.innerHTML = `<span class="log-time">[${time}]</span> <span class="log-${type}">${message}</span>`;
            area.insertBefore(entry, area.firstChild);
            while (area.children.length > 50) area.removeChild(area.lastChild);
        }
        
        async function fetchAPI(endpoint, options = {}) {
            const headers = { 'Content-Type': 'application/json' };
            if (authToken) headers['Authorization'] = `Bearer ${authToken}`;
            
            const res = await fetch(API_BASE + endpoint, { ...options, headers });
            if (res.status === 401) {
                log('response', '⚠ Authentication required. Set token in localStorage.');
            }
            return res.json();
        }
        
        async function refreshStatus() {
            try {
                const data = await fetchAPI('/api/status');
                updateStatus(data);
            } catch (e) {
                document.getElementById('statusBadge').textContent = 'OFFLINE';
                document.getElementById('statusBadge').className = 'status-badge status-offline';
            }
        }
        
        function updateStatus(data) {
            const badge = document.getElementById('statusBadge');
            if (data.running) {
                badge.textContent = 'ONLINE';
                badge.className = 'status-badge status-online';
            } else {
                badge.textContent = 'OFFLINE';
                badge.className = 'status-badge status-offline';
            }
            
            // Update modules
            const modulesList = document.getElementById('modulesList');
            const allModulesList = document.getElementById('allModulesList');
            modulesList.innerHTML = '';
            allModulesList.innerHTML = '';
            
            for (const [name, mod] of Object.entries(data.modules || {})) {
                const item = document.createElement('div');
                item.className = 'module-item';
                item.innerHTML = `
                    <div class="module-info">
                        <span class="module-name">${name}</span>
                        <span class="module-summary">${mod.summary}</span>
                    </div>
                    <div class="module-status ${mod.loaded ? 'status-loaded' : 'status-unloaded'}" title="${mod.loaded ? 'Loaded' : 'Not Loaded'}"></div>
                `;
                modulesList.appendChild(item.cloneNode(true));
                allModulesList.appendChild(item);
            }
            
            // Update tasks
            const tasksList = document.getElementById('tasksList');
            const tasks = [];
            if (data.tasks) {
                // We'd need to fetch tasks separately for full list
            }
            fetchAPI('/api/tasks').then(t => {
                tasksList.innerHTML = '';
                const allTasks = [...(t.pending || []), ...(t.overdue || [])];
                if (allTasks.length === 0) {
                    tasksList.innerHTML = '<div class="task-item"><span class="task-title">No tasks</span></div>';
                } else {
                    for (const task of allTasks) {
                        const item = document.createElement('div');
                        item.className = `task-item ${task.status === 'pending' && new Date(task.deadline) < new Date() ? 'task-overdue' : 'task-pending'}`;
                        item.innerHTML = `
                            <div>
                                <div class="task-title">${task.title}</div>
                                <div class="task-meta">#${task.id} • ${task.category} • ${task.deadline ? 'Due: ' + task.deadline : 'No deadline'}</div>
                            </div>
                            <button class="btn btn-secondary" style="padding: 0.25rem 0.5rem; font-size: 0.75rem;" onclick="completeTask(${task.id})">Done</button>
                        `;
                        tasksList.appendChild(item);
                    }
                }
            });
        }
        
        async function sendCommand() {
            const input = document.getElementById('commandInput');
            const command = input.value.trim();
            if (!command) return;
            
            log('command', `> ${command}`);
            input.value = '';
            
            try {
                const res = await fetchAPI('/api/command', {
                    method: 'POST',
                    body: JSON.stringify({ command })
                });
                log('response', `✓ ${res.status}`);
            } catch (e) {
                log('response', `✗ Error: ${e}`);
            }
        }
        
        async function completeTask(id) {
            try {
                await fetchAPI(`/api/tasks/${id}/complete`, { method: 'POST' });
                log('response', `✓ Task #${id} completed`);
                refreshStatus();
            } catch (e) {
                log('response', `✗ Error: ${e}`);
            }
        }
        
        async function triggerBriefing(type) {
            log('command', `> Briefing: ${type}`);
            try {
                await fetchAPI('/api/briefing', {
                    method: 'POST',
                    body: JSON.stringify({ type })
                });
                log('response', `✓ Briefing started`);
            } catch (e) {
                log('response', `✗ Error: ${e}`);
            }
        }
        
        function showTab(tab) {
            document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
            document.querySelectorAll('.tab-panel').forEach(p => p.classList.remove('active'));
            document.querySelector(`.tab[onclick="showTab('${tab}')"]`).classList.add('active');
            document.getElementById(`tab-${tab}`).classList.add('active');
        }
        
        // Auto-refresh
        setInterval(refreshStatus, 5000);
        refreshStatus();
        
        // Load config tab
        fetchAPI('/api/config').then(cfg => {
            const section = document.getElementById('configSection');
            section.innerHTML = '';
            function addConfig(path, obj, prefix = '') {
                for (const [key, value] of Object.entries(obj)) {
                    const fullPath = prefix + key;
                    if (typeof value === 'object' && value !== null && !Array.isArray(value)) {
                        addConfig(fullPath + '.', value);
                    } else {
                        const item = document.createElement('div');
                        item.className = 'config-item';
                        if (typeof value === 'boolean') {
                            item.innerHTML = `
                                <span class="config-label">${fullPath}</span>
                                <div class="toggle ${value ? 'active' : ''}" onclick="toggleConfig('${fullPath}', ${!value})"></div>
                            `;
                        } else {
                            item.innerHTML = `
                                <span class="config-label">${fullPath}</span>
                                <span class="config-value">${JSON.stringify(value)}</span>
                            `;
                        }
                        section.appendChild(item);
                    }
                }
            }
            addConfig('', cfg);
        });
        
        function toggleConfig(path, value) {
            fetchAPI('/api/config', {
                method: 'PUT',
                body: JSON.stringify({ [path]: value })
            }).then(() => {
                document.querySelector(`[onclick="toggleConfig('${path}', ${!value})"]`).classList.toggle('active');
            });
        }
    </script>
</body>
</html>
"""


def start_api_server(jarvis, voice, brain_instance, tasks):
    """Start the API server in a background thread."""
    global jarvis_instance, voice_engine, brain, task_manager
    jarvis_instance = jarvis
    voice_engine = voice
    brain = brain_instance
    task_manager = tasks
    
    cfg = config.get()
    if not cfg.api.enabled:
        return None
    
    def run():
        app.run(host=cfg.api.host, port=cfg.api.port, debug=False, use_reloader=False)
    
    thread = threading.Thread(target=run, daemon=True)
    thread.start()
    return thread