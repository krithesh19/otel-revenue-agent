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
from fastapi.responses import HTMLResponse, StreamingResponse
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
                # Get reservation_stay_status_sha256
                cur.execute("""
                    SELECT reservation_id, stay_date::text, financial_status
                    FROM public.reservations_hackathon
                    ORDER BY reservation_id, stay_date, financial_status
                """)
                rows = cur.fetchall()
                lines = [f"{r['reservation_id']}|{r['stay_date']}|{r['financial_status']}" for r in rows]
                db_fingerprint = hashlib.sha256("\n".join(lines).encode()).hexdigest()

                # Get load manifest
                cur.execute("SELECT dataset_revision, row_hash, scraped_at FROM public.load_manifest ORDER BY load_id DESC LIMIT 1")
                manifest = cur.fetchone()

                # Get posted stay rows count
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


# Store conversation history per session
conversation_history = {}


@app.post("/chat")
def chat(request: ChatRequest, username: str = Depends(verify_credentials)):
    """Send a message to the Revenue Manager Agent."""
    try:
        from agent.agent import get_agent
        agent = get_agent()

        # Get or create session history
        session_id = request.session_id
        if session_id not in conversation_history:
            conversation_history[session_id] = []

        # Add user message
        conversation_history[session_id].append({
            "role": "user",
            "content": request.message
        })

        # Invoke agent with full history
        result = agent.invoke({
            "messages": conversation_history[session_id]
        })

        # Extract response
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

            # Add assistant response to history
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
    """Simple chat UI for the Revenue Manager Agent."""
    return """
<!DOCTYPE html>
<html>
<head>
    <title>Grand Harbour Hotel — Revenue Manager Agent</title>
    <style>
        body { font-family: Arial, sans-serif; max-width: 900px; margin: 0 auto; padding: 20px; background: #1a1a2e; color: #eee; }
        h1 { color: #00d4ff; border-bottom: 2px solid #00d4ff; padding-bottom: 10px; }
        #chat-box { height: 500px; overflow-y: auto; border: 1px solid #333; padding: 15px; background: #16213e; border-radius: 8px; margin-bottom: 15px; }
        .user-msg { background: #0f3460; padding: 10px; border-radius: 8px; margin: 8px 0; text-align: right; }
        .agent-msg { background: #1a1a2e; border: 1px solid #00d4ff; padding: 10px; border-radius: 8px; margin: 8px 0; white-space: pre-wrap; }
        .tools-used { font-size: 11px; color: #888; margin-top: 5px; }
        .tool-badge { background: #0f3460; padding: 2px 6px; border-radius: 4px; margin-right: 4px; color: #00d4ff; }
        #input-row { display: flex; gap: 10px; }
        #msg-input { flex: 1; padding: 12px; border: 1px solid #333; background: #16213e; color: #eee; border-radius: 8px; font-size: 14px; }
        #send-btn { padding: 12px 24px; background: #00d4ff; color: #000; border: none; border-radius: 8px; cursor: pointer; font-weight: bold; }
        #send-btn:hover { background: #00a8cc; }
        #send-btn:disabled { background: #333; color: #666; cursor: not-allowed; }
        .loading { color: #888; font-style: italic; }
        .examples { margin-bottom: 15px; }
        .example-btn { background: #0f3460; border: 1px solid #00d4ff; color: #00d4ff; padding: 6px 12px; border-radius: 4px; cursor: pointer; margin: 3px; font-size: 12px; }
        .example-btn:hover { background: #00d4ff; color: #000; }
    </style>
</head>
<body>
    <h1>🏨 Grand Harbour Hotel — Revenue Manager Agent</h1>
    <div class="examples">
        <strong>Try asking:</strong><br>
        <button class="example-btn" onclick="setMsg('What revenue is on the books by month?')">Revenue by month</button>
        <button class="example-btn" onclick="setMsg('Which segments are driving July?')">July drivers</button>
        <button class="example-btn" onclick="setMsg('Are we too dependent on OTA?')">OTA dependency</button>
        <button class="example-btn" onclick="setMsg('What changed in the last 7 days for future stays?')">Recent pickup</button>
        <button class="example-btn" onclick="setMsg('How much group business do we have?')">Group mix</button>
        <button class="example-btn" onclick="setMsg('How much business was cancelled in the dataset?')">Cancellations</button>
    </div>
    <div id="chat-box"></div>
    <div id="input-row">
        <input id="msg-input" type="text" placeholder="Ask a revenue management question..." onkeypress="if(event.key==='Enter') sendMsg()">
        <button id="send-btn" onclick="sendMsg()">Send</button>
    </div>

    <script>
        const sessionId = 'session_' + Date.now();
        
        function setMsg(text) {
            document.getElementById('msg-input').value = text;
        }
        
        function addMsg(text, isUser, tools, skills) {
            const box = document.getElementById('chat-box');
            const div = document.createElement('div');
            div.className = isUser ? 'user-msg' : 'agent-msg';
            div.textContent = text;
            
            if (!isUser && (tools?.length || skills?.length)) {
                const toolsDiv = document.createElement('div');
                toolsDiv.className = 'tools-used';
                if (tools?.length) {
                    toolsDiv.innerHTML += '🔧 Tools: ' + tools.map(t => `<span class="tool-badge">${t}</span>`).join('');
                }
                if (skills?.length) {
                    toolsDiv.innerHTML += ' 📚 Skills: ' + skills.map(s => `<span class="tool-badge">${s}</span>`).join('');
                }
                div.appendChild(toolsDiv);
            }
            
            box.appendChild(div);
            box.scrollTop = box.scrollHeight;
        }
        
        async function sendMsg() {
            const input = document.getElementById('msg-input');
            const btn = document.getElementById('send-btn');
            const msg = input.value.trim();
            if (!msg) return;
            
            addMsg(msg, true);
            input.value = '';
            btn.disabled = true;
            
            const loadingDiv = document.createElement('div');
            loadingDiv.className = 'agent-msg loading';
            loadingDiv.id = 'loading';
            loadingDiv.textContent = 'Revenue Manager is thinking...';
            document.getElementById('chat-box').appendChild(loadingDiv);
            
            try {
                const resp = await fetch('/chat', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({message: msg, session_id: sessionId})
                });
                
                document.getElementById('loading')?.remove();
                
                if (resp.ok) {
                    const data = await resp.json();
                    addMsg(data.response, false, data.tools_used, data.skills_loaded);
                } else {
                    const err = await resp.json();
                    addMsg('Error: ' + (err.detail || 'Unknown error'), false);
                }
            } catch(e) {
                document.getElementById('loading')?.remove();
                addMsg('Connection error: ' + e.message, false);
            }
            
            btn.disabled = false;
            input.focus();
        }
    </script>
</body>
</html>
"""


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
