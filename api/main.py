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
            --bg: #080c14;
            --bg2: #0d1420;
            --bg3: #131d2e;
            --card: #172032;
            --accent: #4f8ef7;
            --accent2: #7eb3ff;
            --gold: #f0a500;
            --gold2: #ffc840;
            --green: #22c55e;
            --border: #1e2e45;
            --border2: #263a55;
            --t1: #ffffff;
            --t2: #e2e8f0;
            --t3: #94a3b8;
            --t4: #64748b;
            --user: #1a3a6b;
        }

        body {
            font-family: 'Inter', sans-serif;
            background: var(--bg);
            color: var(--t1);
            height: 100vh;
            display: flex;
            flex-direction: column;
            overflow: hidden;
        }

        /* HEADER */
        header {
            background: var(--bg2);
            border-bottom: 1px solid var(--border);
            padding: 0 28px;
            height: 62px;
            display: flex;
            align-items: center;
            justify-content: space-between;
            flex-shrink: 0;
            box-shadow: 0 1px 20px rgba(0,0,0,0.4);
        }

        .h-left { display: flex; align-items: center; gap: 12px; }

        .logo {
            width: 36px; height: 36px;
            background: linear-gradient(135deg, var(--gold), #d48800);
            border-radius: 9px;
            display: flex; align-items: center; justify-content: center;
            font-size: 17px;
            box-shadow: 0 0 18px rgba(240,165,0,0.35);
            flex-shrink: 0;
        }

        .h-title { font-size: 15px; font-weight: 650; color: var(--t1); letter-spacing: 0.01em; }
        .h-sub { font-size: 11px; color: var(--t3); margin-top: 1px; }

        .h-right { display: flex; align-items: center; gap: 12px; }

        .live-pill {
            display: flex; align-items: center; gap: 6px;
            background: rgba(34,197,94,0.12);
            border: 1px solid rgba(34,197,94,0.3);
            border-radius: 20px; padding: 4px 12px;
            font-size: 11px; font-weight: 600; color: var(--green);
        }
        .live-dot { width: 6px; height: 6px; background: var(--green); border-radius: 50%; animation: blink 2s infinite; }
        @keyframes blink { 0%,100%{opacity:1} 50%{opacity:0.3} }

        .model-tag {
            font-size: 11px; color: var(--t4);
            background: var(--card); border: 1px solid var(--border);
            border-radius: 6px; padding: 4px 10px;
        }

        /* CHIPS BAR */
        .chips {
            background: var(--bg2);
            border-bottom: 1px solid var(--border);
            padding: 10px 28px;
            display: flex; gap: 8px; flex-wrap: wrap;
            flex-shrink: 0;
        }

        .chip {
            background: var(--bg3);
            border: 1px solid var(--border2);
            color: var(--t2);
            padding: 6px 14px; border-radius: 20px;
            font-size: 12px; font-weight: 500;
            cursor: pointer; transition: all 0.18s;
            font-family: 'Inter', sans-serif;
            white-space: nowrap;
        }
        .chip:hover { background: rgba(79,142,247,0.15); border-color: var(--accent); color: var(--accent2); }

        /* CHAT */
        #box {
            flex: 1; overflow-y: auto; padding: 28px;
            display: flex; flex-direction: column; gap: 20px;
            scroll-behavior: smooth;
        }
        #box::-webkit-scrollbar { width: 4px; }
        #box::-webkit-scrollbar-thumb { background: var(--border2); border-radius: 4px; }

        /* WELCOME */
        .welcome {
            display: flex; flex-direction: column; align-items: center;
            justify-content: center; flex: 1; text-align: center;
            gap: 16px; margin: auto; padding: 40px;
        }

        .welcome-icon-wrap {
            width: 72px; height: 72px;
            background: linear-gradient(135deg, rgba(240,165,0,0.2), rgba(240,165,0,0.05));
            border: 1px solid rgba(240,165,0,0.3);
            border-radius: 20px;
            display: flex; align-items: center; justify-content: center;
            font-size: 32px;
            box-shadow: 0 0 30px rgba(240,165,0,0.15);
            margin-bottom: 4px;
        }

        .welcome h2 {
            font-size: 22px; font-weight: 700;
            color: #ffffff;
            letter-spacing: -0.01em;
        }

        .welcome p {
            font-size: 14px; color: #94a3b8;
            max-width: 380px; line-height: 1.75;
        }

        .welcome-stats {
            display: flex; gap: 24px; margin-top: 8px;
        }

        .stat {
            display: flex; flex-direction: column; align-items: center; gap: 4px;
            background: var(--card); border: 1px solid var(--border2);
            border-radius: 12px; padding: 12px 20px;
            min-width: 90px;
        }

        .stat-val { font-size: 18px; font-weight: 700; color: var(--accent2); }
        .stat-lbl { font-size: 10px; color: var(--t4); text-transform: uppercase; letter-spacing: 0.05em; }

        /* MESSAGES */
        .row { display: flex; gap: 10px; max-width: 840px; width: 100%; }
        .row.user { margin-left: auto; flex-direction: row-reverse; }

        .av {
            width: 34px; height: 34px; border-radius: 9px;
            display: flex; align-items: center; justify-content: center;
            font-size: 15px; flex-shrink: 0; margin-top: 2px;
        }
        .av.agent { background: linear-gradient(135deg, var(--accent), #2563eb); }
        .av.user { background: var(--user); border: 1px solid var(--border2); }

        .mc { display: flex; flex-direction: column; gap: 5px; min-width: 0; }

        .bubble {
            padding: 13px 17px; border-radius: 13px;
            font-size: 13.5px; line-height: 1.7;
            white-space: pre-wrap; word-break: break-word;
        }

        .row.agent .bubble {
            background: var(--card);
            border: 1px solid var(--border2);
            border-top-left-radius: 4px;
            color: #e8edf5;
        }

        .row.user .bubble {
            background: var(--user);
            border: 1px solid #2a4a80;
            border-top-right-radius: 4px;
            color: #ddeeff;
        }

        .meta { display: flex; align-items: center; gap: 6px; padding: 0 4px; flex-wrap: wrap; }
        .time { font-size: 10px; color: var(--t4); }

        .badges { display: flex; gap: 4px; flex-wrap: wrap; }
        .badge {
            font-size: 10px; font-family: monospace;
            background: rgba(79,142,247,0.12);
            border: 1px solid rgba(79,142,247,0.25);
            color: var(--accent2);
            padding: 2px 7px; border-radius: 4px;
        }

        /* TYPING */
        .typing { display: flex; gap: 5px; align-items: center; padding: 14px 18px; }
        .td { width: 7px; height: 7px; background: var(--accent); border-radius: 50%; animation: bounce 1.2s infinite; }
        .td:nth-child(2){animation-delay:.2s} .td:nth-child(3){animation-delay:.4s}
        @keyframes bounce { 0%,60%,100%{transform:translateY(0);opacity:.4} 30%{transform:translateY(-7px);opacity:1} }

        /* INPUT */
        .inputbar {
            background: var(--bg2);
            border-top: 1px solid var(--border);
            padding: 16px 28px; flex-shrink: 0;
        }

        .inputwrap {
            display: flex; gap: 10px; align-items: flex-end;
            background: var(--bg3);
            border: 1.5px solid var(--border2);
            border-radius: 13px; padding: 10px 10px 10px 16px;
            transition: border-color 0.2s, box-shadow 0.2s;
        }
        .inputwrap:focus-within {
            border-color: var(--accent);
            box-shadow: 0 0 0 3px rgba(79,142,247,0.12);
        }

        #inp {
            flex: 1; background: transparent; border: none; outline: none;
            color: #f0f4ff; font-family: 'Inter', sans-serif;
            font-size: 13.5px; resize: none;
            min-height: 22px; max-height: 120px; line-height: 1.55;
        }
        #inp::placeholder { color: var(--t4); }

        #sbtn {
            width: 38px; height: 38px;
            background: var(--accent); border: none; border-radius: 9px;
            cursor: pointer; display: flex; align-items: center; justify-content: center;
            transition: all 0.18s; flex-shrink: 0;
        }
        #sbtn:hover { background: #3a7af0; transform: scale(1.06); }
        #sbtn:disabled { background: var(--border2); cursor: not-allowed; transform: none; }
        #sbtn svg { width: 16px; height: 16px; fill: white; }

        .hint { font-size: 11px; color: var(--t4); margin-top: 8px; text-align: center; }
    </style>
</head>
<body>

<header>
    <div class="h-left">
        <div class="logo">🏨</div>
        <div>
            <div class="h-title">Grand Harbour Hotel — Revenue Intelligence</div>
            <div class="h-sub">AI Revenue Manager · Ireland · Live data 2026 · Built by Kritheshvar Vinothkumar</div>
        </div>
    </div>
    <div class="h-right">
        <div class="live-pill"><div class="live-dot"></div>Live</div>
        <div class="model-tag">GPT-4o mini · 5 tools · 6 skills</div>
    </div>
</header>

<div class="chips">
    <button class="chip" onclick="send('What is the on-the-books revenue by month for 2026?')">📊 Revenue by month</button>
    <button class="chip" onclick="send('Which segments are driving July 2026 revenue?')">🎯 July 2026 drivers</button>
    <button class="chip" onclick="send('Are we too dependent on OTA for August 2026?')">⚠️ OTA dependency</button>
    <button class="chip" onclick="send('What new bookings came in over the last 7 days for future 2026 stays?')">📈 Recent pickup</button>
    <button class="chip" onclick="send('How much group vs transient business do we have for July 2026?')">🏢 Group vs transient</button>
    <button class="chip" onclick="send('What was the cancellation revenue impact across all months?')">❌ Cancellation impact</button>
</div>

<div id="box">
    <div class="welcome" id="welcome">
        <div class="welcome-icon-wrap">🏨</div>
        <h2>Good morning, General Manager</h2>
        <p>Your AI Revenue Manager is ready. Ask me about revenue on the books, booking pace, segment mix, group business, or cancellation trends for Grand Harbour Hotel.</p>
        <div class="welcome-stats">
            <div class="stat"><span class="stat-val">254</span><span class="stat-lbl">Reservations</span></div>
            <div class="stat"><span class="stat-val">98</span><span class="stat-lbl">Rooms</span></div>
            <div class="stat"><span class="stat-val">5</span><span class="stat-lbl">Tools</span></div>
            <div class="stat"><span class="stat-val">6</span><span class="stat-lbl">Skills</span></div>
        </div>
    </div>
</div>

<div class="inputbar">
    <div class="inputwrap">
        <textarea id="inp" rows="1" placeholder="Ask a revenue management question..." onkeydown="handleKey(event)"></textarea>
        <button id="sbtn" onclick="sendMsg()" title="Send">
            <svg viewBox="0 0 24 24"><path d="M2.01 21L23 12 2.01 3 2 10l15 2-15 2z"/></svg>
        </button>
    </div>
    <div class="hint">Press Enter to send · Shift+Enter for new line</div>
</div>

<script>
    const sid = 'session_' + Date.now();
    const inp = document.getElementById('inp');

    inp.addEventListener('input', function() {
        this.style.height = 'auto';
        this.style.height = Math.min(this.scrollHeight, 120) + 'px';
    });

    function handleKey(e) {
        if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendMsg(); }
    }

    function send(t) { inp.value = t; sendMsg(); }

    function ts() { return new Date().toLocaleTimeString('en-IE', {hour:'2-digit', minute:'2-digit'}); }

    function esc(s) { return s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;'); }

    function rmWelcome() { document.getElementById('welcome')?.remove(); }

    function addUser(text) {
        rmWelcome();
        const box = document.getElementById('box');
        const d = document.createElement('div');
        d.className = 'row user';
        d.innerHTML = `<div class="av user">👤</div><div class="mc"><div class="bubble">${esc(text)}</div><div class="meta" style="justify-content:flex-end"><span class="time">${ts()}</span></div></div>`;
        box.appendChild(d);
        box.scrollTop = box.scrollHeight;
    }

    function addTyping() {
        const box = document.getElementById('box');
        const d = document.createElement('div');
        d.className = 'row agent'; d.id = 'typing';
        d.innerHTML = `<div class="av agent">🤖</div><div class="mc"><div class="bubble"><div class="typing"><div class="td"></div><div class="td"></div><div class="td"></div></div></div></div>`;
        box.appendChild(d);
        box.scrollTop = box.scrollHeight;
    }

    function rmTyping() { document.getElementById('typing')?.remove(); }

    function addAgent(text, tools, skills) {
        const box = document.getElementById('box');
        const d = document.createElement('div');
        d.className = 'row agent';
        const all = [...(tools||[]), ...(skills||[])];
        const badgesHtml = all.length ? '<div class="badges">' + all.map(t=>`<span class="badge">${t}</span>`).join('') + '</div>' : '';
        d.innerHTML = `<div class="av agent">🤖</div><div class="mc"><div class="bubble">${esc(text)}</div><div class="meta"><span class="time">${ts()}</span>${badgesHtml}</div></div>`;
        box.appendChild(d);
        box.scrollTop = box.scrollHeight;
    }

    async function sendMsg() {
        const btn = document.getElementById('sbtn');
        const msg = inp.value.trim();
        if (!msg) return;
        addUser(msg);
        inp.value = ''; inp.style.height = 'auto';
        btn.disabled = true;
        addTyping();

        try {
            const r = await fetch('/chat', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({message: msg, session_id: sid})
            });
            rmTyping();
            if (r.ok) {
                const d = await r.json();
                addAgent(d.response, d.tools_used, d.skills_loaded);
            } else {
                const e = await r.json();
                addAgent('Error: ' + (e.detail || 'Unknown error'), [], []);
            }
        } catch(e) {
            rmTyping();
            addAgent('Connection error: ' + e.message, [], []);
        }
        btn.disabled = false;
        inp.focus();
    }
</script>
</body>
</html>"""


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)