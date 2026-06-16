"""
Phase 4 — FastAPI backend for Revenue Manager Agent.
Endpoints:
- GET /health — DB fingerprint check
- POST /chat — Send message to agent
- GET / — Simple chat UI
"""
import hashlib
import os
import sys
from pathlib import Path
from datetime import datetime, timezone

from dotenv import load_dotenv
load_dotenv()

sys.path.insert(0, str(Path(__file__).parent.parent))

from fastapi import FastAPI, HTTPException, Depends
from fastapi.responses import HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from pydantic import BaseModel
import psycopg
from psycopg.rows import dict_row
import secrets

app = FastAPI(title="Revenue Manager Agent API")
security = HTTPBasic()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

DATABASE_URL = os.environ.get("DATABASE_URL", "")
AGENT_USERNAME = os.environ.get("AGENT_USERNAME", "otel")
AGENT_PASSWORD = os.environ.get("AGENT_PASSWORD", "revenue2026")


def verify_credentials(credentials: HTTPBasicCredentials = Depends(security)):
    correct_user = secrets.compare_digest(credentials.username, AGENT_USERNAME)
    correct_pass = secrets.compare_digest(credentials.password, AGENT_PASSWORD)
    if not (correct_user and correct_pass):
        raise HTTPException(status_code=401, detail="Unauthorized",
                            headers={"WWW-Authenticate": "Basic"})
    return credentials.username


def get_conn():
    return psycopg.connect(DATABASE_URL, row_factory=dict_row, prepare_threshold=0)


@app.get("/health")
def health():
    """Health check — returns DB fingerprint for submission verification."""
    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT reservation_id, stay_date::text, financial_status
                    FROM public.reservations_hackathon
                    ORDER BY reservation_id, stay_date, financial_status
                """)
                rows = cur.fetchall()
                lines = [f"{r['reservation_id']}|{r['stay_date']}|{r['financial_status']}" for r in rows]
                db_fingerprint = hashlib.sha256("\n".join(lines).encode()).hexdigest()

                cur.execute("SELECT dataset_revision, row_hash, scraped_at FROM public.load_manifest ORDER BY load_id DESC LIMIT 1")
                manifest = cur.fetchone()

                cur.execute("SELECT COUNT(*) as n FROM public.reservations_hackathon WHERE reservation_status <> 'Cancelled' AND financial_status = 'Posted'")
                posted = cur.fetchone()

        return {
            "status": "healthy",
            "db_fingerprint": db_fingerprint,
            "dataset_revision": manifest["dataset_revision"] if manifest else None,
            "row_hash": manifest["row_hash"] if manifest else None,
            "financial_status_posted_only_rows": posted["n"],
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


class ChatRequest(BaseModel):
    message: str
    session_id: str = "default"


class ChatResponse(BaseModel):
    response: str
    tools_used: list = []
    skills_loaded: list = []


conversation_history = {}


@app.post("/chat")
def chat(request: ChatRequest, username: str = Depends(verify_credentials)):
    """Send a message to the Revenue Manager Agent."""
    try:
        from agent.agent import get_agent
        agent = get_agent()

        session_id = request.session_id
        if session_id not in conversation_history:
            conversation_history[session_id] = []

        conversation_history[session_id].append({
            "role": "user",
            "content": request.message
        })

        result = agent.invoke(
            {"messages": conversation_history[session_id]},
            config={"configurable": {"thread_id": session_id}}
        )

        response_text = ""
        tools_used = []
        skills_loaded = []

        if isinstance(result, dict) and "messages" in result:
            messages = result["messages"]
            for msg in messages:
                if hasattr(msg, "tool_calls") and msg.tool_calls:
                    for tc in msg.tool_calls:
                        tool_name = tc.get("name", "") if isinstance(tc, dict) else getattr(tc, "name", "")
                        if tool_name:
                            if "skill" in tool_name.lower() or tool_name == "read_file":
                                skills_loaded.append(tool_name)
                            else:
                                tools_used.append(tool_name)

            last_msg = messages[-1]
            response_text = last_msg.content if hasattr(last_msg, "content") else str(last_msg)

            conversation_history[session_id].append({
                "role": "assistant",
                "content": response_text
            })

        return ChatResponse(
            response=response_text,
            tools_used=list(set(tools_used)),
            skills_loaded=list(set(skills_loaded)),
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/", response_class=HTMLResponse)
def chat_ui(username: str = Depends(verify_credentials)):
    return """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Grand Harbour Hotel — Revenue Intelligence</title>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap" rel="stylesheet">
    <style>
        *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }

        :root {
            --bg-primary: #0a0e1a;
            --bg-secondary: #111827;
            --bg-card: #1a2235;
            --bg-input: #0f1724;
            --accent: #3b82f6;
            --accent-glow: rgba(59,130,246,0.15);
            --accent-light: #60a5fa;
            --gold: #f59e0b;
            --gold-light: #fcd34d;
            --text-primary: #f1f5f9;
            --text-secondary: #94a3b8;
            --text-muted: #475569;
            --border: #1e2d45;
            --border-light: #2d3f5a;
            --success: #10b981;
            --user-bg: #1e3a5f;
        }

        body {
            font-family: 'Inter', sans-serif;
            background: var(--bg-primary);
            color: var(--text-primary);
            height: 100vh;
            display: flex;
            flex-direction: column;
            overflow: hidden;
        }

        /* ── HEADER ── */
        header {
            background: var(--bg-secondary);
            border-bottom: 1px solid var(--border);
            padding: 0 24px;
            height: 64px;
            display: flex;
            align-items: center;
            justify-content: space-between;
            flex-shrink: 0;
        }

        .header-left {
            display: flex;
            align-items: center;
            gap: 14px;
        }

        .hotel-icon {
            width: 38px;
            height: 38px;
            background: linear-gradient(135deg, var(--gold), #d97706);
            border-radius: 10px;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 18px;
            box-shadow: 0 0 16px rgba(245,158,11,0.3);
        }

        .header-text h1 {
            font-size: 15px;
            font-weight: 600;
            color: var(--text-primary);
            letter-spacing: 0.01em;
        }

        .header-text p {
            font-size: 11px;
            color: var(--text-muted);
            margin-top: 1px;
        }

        .header-right {
            display: flex;
            align-items: center;
            gap: 16px;
        }

        .status-pill {
            display: flex;
            align-items: center;
            gap: 6px;
            background: rgba(16,185,129,0.1);
            border: 1px solid rgba(16,185,129,0.25);
            border-radius: 20px;
            padding: 4px 12px;
            font-size: 11px;
            color: var(--success);
            font-weight: 500;
        }

        .status-dot {
            width: 6px;
            height: 6px;
            background: var(--success);
            border-radius: 50%;
            animation: pulse 2s infinite;
        }

        @keyframes pulse {
            0%, 100% { opacity: 1; }
            50% { opacity: 0.4; }
        }

        .model-badge {
            font-size: 11px;
            color: var(--text-muted);
            background: var(--bg-card);
            border: 1px solid var(--border);
            border-radius: 6px;
            padding: 4px 10px;
        }

        /* ── QUICK PROMPTS ── */
        .prompts-bar {
            background: var(--bg-secondary);
            border-bottom: 1px solid var(--border);
            padding: 10px 24px;
            display: flex;
            gap: 8px;
            flex-wrap: wrap;
            flex-shrink: 0;
        }

        .prompt-chip {
            background: var(--bg-card);
            border: 1px solid var(--border-light);
            color: var(--text-secondary);
            padding: 5px 12px;
            border-radius: 20px;
            font-size: 12px;
            cursor: pointer;
            transition: all 0.2s;
            font-family: 'Inter', sans-serif;
            white-space: nowrap;
        }

        .prompt-chip:hover {
            background: var(--accent-glow);
            border-color: var(--accent);
            color: var(--accent-light);
        }

        /* ── CHAT AREA ── */
        #chat-box {
            flex: 1;
            overflow-y: auto;
            padding: 24px;
            display: flex;
            flex-direction: column;
            gap: 16px;
            scroll-behavior: smooth;
        }

        #chat-box::-webkit-scrollbar { width: 4px; }
        #chat-box::-webkit-scrollbar-track { background: transparent; }
        #chat-box::-webkit-scrollbar-thumb { background: var(--border-light); border-radius: 4px; }

        /* Welcome state */
        .welcome {
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: center;
            flex: 1;
            text-align: center;
            gap: 12px;
            opacity: 0.6;
            margin: auto;
            padding: 40px;
        }

        .welcome-icon { font-size: 40px; }
        .welcome h2 { font-size: 16px; font-weight: 500; color: var(--text-secondary); }
        .welcome p { font-size: 13px; color: var(--text-muted); max-width: 340px; line-height: 1.6; }

        /* Messages */
        .msg-row {
            display: flex;
            gap: 10px;
            max-width: 820px;
            width: 100%;
        }

        .msg-row.user { margin-left: auto; flex-direction: row-reverse; }

        .avatar {
            width: 32px;
            height: 32px;
            border-radius: 8px;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 14px;
            flex-shrink: 0;
            margin-top: 2px;
        }

        .avatar.agent { background: linear-gradient(135deg, var(--accent), #1d4ed8); }
        .avatar.user { background: var(--user-bg); border: 1px solid var(--border-light); }

        .msg-content { display: flex; flex-direction: column; gap: 4px; min-width: 0; }

        .msg-bubble {
            padding: 12px 16px;
            border-radius: 12px;
            font-size: 13.5px;
            line-height: 1.65;
            white-space: pre-wrap;
            word-break: break-word;
        }

        .msg-row.agent .msg-bubble {
            background: var(--bg-card);
            border: 1px solid var(--border);
            border-top-left-radius: 4px;
            color: var(--text-primary);
        }

        .msg-row.user .msg-bubble {
            background: var(--user-bg);
            border: 1px solid #2d4a6b;
            border-top-right-radius: 4px;
            color: var(--text-primary);
        }

        .msg-meta {
            display: flex;
            align-items: center;
            gap: 8px;
            padding: 0 4px;
        }

        .msg-time {
            font-size: 10px;
            color: var(--text-muted);
        }

        .tool-badges {
            display: flex;
            gap: 4px;
            flex-wrap: wrap;
        }

        .tool-badge {
            font-size: 10px;
            font-family: 'Inter', monospace;
            background: rgba(59,130,246,0.1);
            border: 1px solid rgba(59,130,246,0.2);
            color: var(--accent-light);
            padding: 1px 7px;
            border-radius: 4px;
        }

        /* Typing indicator */
        .typing-bubble {
            background: var(--bg-card);
            border: 1px solid var(--border);
            border-top-left-radius: 4px;
            padding: 14px 18px;
            border-radius: 12px;
            display: flex;
            align-items: center;
            gap: 5px;
        }

        .typing-dot {
            width: 6px;
            height: 6px;
            background: var(--accent);
            border-radius: 50%;
            animation: typing 1.2s infinite;
        }

        .typing-dot:nth-child(2) { animation-delay: 0.2s; }
        .typing-dot:nth-child(3) { animation-delay: 0.4s; }

        @keyframes typing {
            0%, 60%, 100% { transform: translateY(0); opacity: 0.4; }
            30% { transform: translateY(-6px); opacity: 1; }
        }

        /* ── INPUT BAR ── */
        .input-bar {
            background: var(--bg-secondary);
            border-top: 1px solid var(--border);
            padding: 16px 24px;
            flex-shrink: 0;
        }

        .input-inner {
            display: flex;
            gap: 10px;
            align-items: flex-end;
            background: var(--bg-input);
            border: 1px solid var(--border-light);
            border-radius: 12px;
            padding: 10px 10px 10px 16px;
            transition: border-color 0.2s;
        }

        .input-inner:focus-within {
            border-color: var(--accent);
            box-shadow: 0 0 0 3px var(--accent-glow);
        }

        #msg-input {
            flex: 1;
            background: transparent;
            border: none;
            outline: none;
            color: var(--text-primary);
            font-family: 'Inter', sans-serif;
            font-size: 13.5px;
            resize: none;
            min-height: 22px;
            max-height: 120px;
            line-height: 1.5;
        }

        #msg-input::placeholder { color: var(--text-muted); }

        #send-btn {
            width: 36px;
            height: 36px;
            background: var(--accent);
            border: none;
            border-radius: 8px;
            cursor: pointer;
            display: flex;
            align-items: center;
            justify-content: center;
            transition: all 0.2s;
            flex-shrink: 0;
        }

        #send-btn:hover { background: #2563eb; transform: scale(1.05); }
        #send-btn:disabled { background: var(--border-light); cursor: not-allowed; transform: none; }

        #send-btn svg { width: 16px; height: 16px; fill: white; }

        .input-hint {
            font-size: 11px;
            color: var(--text-muted);
            margin-top: 8px;
            text-align: center;
        }
    </style>
</head>
<body>

<header>
    <div class="header-left">
        <div class="hotel-icon">🏨</div>
        <div class="header-text">
            <h1>Grand Harbour Hotel — Revenue Intelligence</h1>
            <p>AI Revenue Manager · Ireland · Live data 2026</p>
        </div>
    </div>
    <div class="header-right">
        <div class="status-pill">
            <div class="status-dot"></div>
            Live
        </div>
        <div class="model-badge">GPT-4o mini · 5 tools · 6 skills</div>
    </div>
</header>

<div class="prompts-bar">
    <button class="prompt-chip" onclick="send('What is the on-the-books revenue by month for 2026?')">📊 Revenue by month</button>
    <button class="prompt-chip" onclick="send('Which segments are driving July 2026 revenue?')">🎯 July 2026 drivers</button>
    <button class="prompt-chip" onclick="send('Are we too dependent on OTA for August 2026?')">⚠️ OTA dependency</button>
    <button class="prompt-chip" onclick="send('What new bookings came in over the last 7 days for future 2026 stays?')">📈 Recent pickup</button>
    <button class="prompt-chip" onclick="send('How much group vs transient business do we have for July 2026?')">🏢 Group vs transient</button>
    <button class="prompt-chip" onclick="send('What was the cancellation revenue impact across all months?')">❌ Cancellation impact</button>
</div>

<div id="chat-box">
    <div class="welcome" id="welcome">
        <div class="welcome-icon">💼</div>
        <h2>Good morning, General Manager</h2>
        <p>Ask me anything about revenue performance, booking pace, segment mix, or group business for Grand Harbour Hotel.</p>
    </div>
</div>

<div class="input-bar">
    <div class="input-inner">
        <textarea id="msg-input" rows="1" placeholder="Ask a revenue management question..." onkeydown="handleKey(event)"></textarea>
        <button id="send-btn" onclick="sendMsg()" title="Send">
            <svg viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">
                <path d="M2.01 21L23 12 2.01 3 2 10l15 2-15 2z"/>
            </svg>
        </button>
    </div>
    <div class="input-hint">Press Enter to send · Shift+Enter for new line</div>
</div>

<script>
    const sessionId = 'session_' + Date.now();
    let messageCount = 0;

    const textarea = document.getElementById('msg-input');
    textarea.addEventListener('input', function() {
        this.style.height = 'auto';
        this.style.height = Math.min(this.scrollHeight, 120) + 'px';
    });

    function handleKey(e) {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            sendMsg();
        }
    }

    function send(text) {
        document.getElementById('msg-input').value = text;
        sendMsg();
    }

    function getTime() {
        return new Date().toLocaleTimeString('en-IE', { hour: '2-digit', minute: '2-digit' });
    }

    function removeWelcome() {
        const w = document.getElementById('welcome');
        if (w) w.remove();
    }

    function addUserMsg(text) {
        removeWelcome();
        messageCount++;
        const box = document.getElementById('chat-box');
        const row = document.createElement('div');
        row.className = 'msg-row user';
        row.innerHTML = `
            <div class="avatar user">👤</div>
            <div class="msg-content">
                <div class="msg-bubble">${escHtml(text)}</div>
                <div class="msg-meta" style="justify-content:flex-end">
                    <span class="msg-time">${getTime()}</span>
                </div>
            </div>`;
        box.appendChild(row);
        box.scrollTop = box.scrollHeight;
    }

    function addTyping() {
        const box = document.getElementById('chat-box');
        const row = document.createElement('div');
        row.className = 'msg-row agent';
        row.id = 'typing-row';
        row.innerHTML = `
            <div class="avatar agent">🤖</div>
            <div class="msg-content">
                <div class="typing-bubble">
                    <div class="typing-dot"></div>
                    <div class="typing-dot"></div>
                    <div class="typing-dot"></div>
                </div>
            </div>`;
        box.appendChild(row);
        box.scrollTop = box.scrollHeight;
    }

    function removeTyping() {
        document.getElementById('typing-row')?.remove();
    }

    function addAgentMsg(text, tools, skills) {
        const box = document.getElementById('chat-box');
        const row = document.createElement('div');
        row.className = 'msg-row agent';

        let metaHtml = `<span class="msg-time">${getTime()}</span>`;
        if (tools?.length || skills?.length) {
            const allBadges = [...(tools || []), ...(skills || [])];
            metaHtml += '<div class="tool-badges">' + allBadges.map(t => `<span class="tool-badge">${t}</span>`).join('') + '</div>';
        }

        row.innerHTML = `
            <div class="avatar agent">🤖</div>
            <div class="msg-content">
                <div class="msg-bubble">${escHtml(text)}</div>
                <div class="msg-meta">${metaHtml}</div>
            </div>`;
        box.appendChild(row);
        box.scrollTop = box.scrollHeight;
    }

    function escHtml(str) {
        return str.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
    }

    async function sendMsg() {
        const input = document.getElementById('msg-input');
        const btn = document.getElementById('send-btn');
        const msg = input.value.trim();
        if (!msg) return;

        addUserMsg(msg);
        input.value = '';
        input.style.height = 'auto';
        btn.disabled = true;
        addTyping();

        try {
            const resp = await fetch('/chat', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({message: msg, session_id: sessionId})
            });

            removeTyping();

            if (resp.ok) {
                const data = await resp.json();
                addAgentMsg(data.response, data.tools_used, data.skills_loaded);
            } else {
                const err = await resp.json();
                addAgentMsg('Error: ' + (err.detail || 'Unknown error'), [], []);
            }
        } catch(e) {
            removeTyping();
            addAgentMsg('Connection error: ' + e.message, [], []);
        }

        btn.disabled = false;
        input.focus();
    }
</script>
</body>
</html>"""


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)