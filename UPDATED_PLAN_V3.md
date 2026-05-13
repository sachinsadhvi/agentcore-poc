
# Implementation Plan V3 — Full System
# Prompt → Deploy Agent → Chat UI → Anyone Can Use It

---

## What's New in V3

V2 solved the backend deployment. V3 adds:
1. A public-facing chat endpoint (so others can access deployed agents)
2. A React chat UI embedded in your FastAPI app (so you AND others can
   talk to any deployed agent from the browser)
3. Conversation history per session (so the agent remembers context)
4. A simple API key for access control (so not just anyone can invoke)

---

## Complete System Architecture

```
┌─────────────────────────────────────────────────────────┐
│  BROWSER (Your App / Anyone with the URL)                │
│                                                          │
│  ┌─────────────────────┐   ┌────────────────────────┐   │
│  │  Build Page          │   │  Chat Page              │   │
│  │  - Type a prompt     │   │  - Pick a deployed agent│   │
│  │  - Select tools      │   │  - Type messages        │   │
│  │  - Click Deploy      │   │  - See streaming replies│   │
│  │  - See live status   │   │  - Full chat history    │   │
│  └──────────┬──────────┘   └──────────┬─────────────┘   │
└─────────────┼────────────────────────-┼─────────────────┘
              │                          │
              ▼                          ▼
┌─────────────────────────────────────────────────────────┐
│  FastAPI Backend (main.py)  — public URL via ECS/EC2     │
│                                                          │
│  Build endpoints:          Chat endpoints:               │
│  POST /workflows/generate  POST /chat/{agent_id}/message │
│  POST /workflows/{id}/deploy GET /chat/{agent_id}/history│
│  GET  /workflows/{id}      GET  /agents                  │
│  GET  /deployments/{id}    DELETE /chat/{agent_id}/session│
│                                                          │
│  Auth: X-API-Key header on all endpoints                 │
└──────────────────────────┬──────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────┐
│  AWS AgentCore Runtime                                   │
│  - boto3 invoke_agent_runtime(ARN, session_id, payload)  │
│  - Session preserved per browser tab (same session_id)   │
│  - Agent visible in AWS console                          │
└─────────────────────────────────────────────────────────┘
```

---

## New File Structure

```
blueprint-poc/
├── main.py                    # FastAPI — all endpoints including chat
├── workflow_generator.py      # Generates agent_handler.py from prompt
├── tool_registry.py           # Tool catalogue
├── workflow_editor.py         # Edit agent code
├── deployment_manager.py      # ECR + create_agent_runtime
├── chat_manager.py            # NEW: session + history management
├── agent_store.py             # NEW: in-memory store for deployed agents
├── static/
│   └── index.html             # NEW: React chat + build UI (single file)
├── requirements.txt
└── .env
```

---

## 1. `chat_manager.py` — NEW FILE

Manages conversation sessions and history. Calls AgentCore Runtime.

```python
import boto3
import json
import uuid
from datetime import datetime
from typing import Optional
from collections import defaultdict

# In-memory session store
# Structure: { agent_id: { session_id: [messages] } }
_sessions: dict = defaultdict(dict)

def get_or_create_session(agent_id: str, session_id: Optional[str] = None) -> str:
    """Return existing session_id or create a new one (must be 33+ chars)."""
    if session_id and session_id in _sessions[agent_id]:
        return session_id
    new_id = f"session-{agent_id[:8]}-{str(uuid.uuid4())}"  # always 33+ chars
    _sessions[agent_id][new_id] = []
    return new_id

def add_to_history(agent_id: str, session_id: str, role: str, content: str):
    if session_id not in _sessions[agent_id]:
        _sessions[agent_id][session_id] = []
    _sessions[agent_id][session_id].append({
        "role": role,
        "content": content,
        "timestamp": datetime.utcnow().isoformat()
    })

def get_history(agent_id: str, session_id: str) -> list:
    return _sessions.get(agent_id, {}).get(session_id, [])

def clear_session(agent_id: str, session_id: str):
    if agent_id in _sessions and session_id in _sessions[agent_id]:
        _sessions[agent_id][session_id] = []

def send_message(
    agent_arn: str,
    agent_id: str,
    session_id: str,
    user_message: str,
    region: str
) -> str:
    """Send a message to AgentCore Runtime and return the response."""

    # Save user message to history
    add_to_history(agent_id, session_id, "user", user_message)

    # Build payload — include conversation history for context
    history = get_history(agent_id, session_id)
    payload = json.dumps({
        "prompt": user_message,
        "history": history[:-1]  # exclude the message we just added
    }).encode()

    # Call AgentCore
    client = boto3.client("bedrock-agentcore", region_name=region)
    response = client.invoke_agent_runtime(
        agentRuntimeArn=agent_arn,
        runtimeSessionId=session_id,
        payload=payload,
        qualifier="DEFAULT"
    )

    # Parse streaming response
    chunks = []
    for chunk in response.get("response", []):
        chunks.append(chunk.decode("utf-8"))
    raw = "".join(chunks)

    try:
        result = json.loads(raw)
        agent_reply = result.get("result", result.get("output", raw))
    except json.JSONDecodeError:
        agent_reply = raw

    # Save agent reply to history
    add_to_history(agent_id, session_id, "assistant", agent_reply)

    return agent_reply
```

---

## 2. `agent_store.py` — NEW FILE

Tracks all deployed agents so the UI can list them.

```python
from typing import Optional
import uuid

# In-memory store — replace with DB later
_agents: dict = {}

def save_agent(
    name: str,
    prompt: str,
    agent_arn: str,
    image_uri: str,
    region: str,
    tools: list
) -> dict:
    agent_id = f"agent-{str(uuid.uuid4())[:8]}"
    record = {
        "agent_id": agent_id,
        "name": name,
        "prompt": prompt,
        "agent_arn": agent_arn,
        "image_uri": image_uri,
        "region": region,
        "tools": tools,
        "status": "READY",
        "console_url": (
            f"https://{region}.console.aws.amazon.com/bedrock-agentcore/agents"
            f"?agentArn={agent_arn}"
        )
    }
    _agents[agent_id] = record
    return record

def get_agent(agent_id: str) -> Optional[dict]:
    return _agents.get(agent_id)

def list_agents() -> list:
    return list(_agents.values())

def update_agent_status(agent_id: str, status: str):
    if agent_id in _agents:
        _agents[agent_id]["status"] = status
```

---

## 3. `main.py` — Updated with Chat + Agent List Endpoints

Add these new endpoints to your existing main.py:

```python
from fastapi import FastAPI, HTTPException, Header, Depends
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
from typing import Optional
import os

from chat_manager import send_message, get_or_create_session, get_history, clear_session
from agent_store import list_agents, get_agent, save_agent

app = FastAPI()
app.mount("/static", StaticFiles(directory="static"), name="static")

API_KEY = os.getenv("APP_API_KEY", "dev-key-change-in-production")
AWS_REGION = os.getenv("AWS_REGION", "us-east-1")

# --- Auth dependency ---
def verify_api_key(x_api_key: str = Header(...)):
    if x_api_key != API_KEY:
        raise HTTPException(status_code=401, detail="Invalid API key")

# --- Serve the UI ---
@app.get("/")
def serve_ui():
    return FileResponse("static/index.html")

# --- List all deployed agents ---
@app.get("/agents", dependencies=[Depends(verify_api_key)])
def get_agents():
    return {"agents": list_agents()}

# --- Chat endpoints ---
class ChatMessage(BaseModel):
    message: str
    session_id: Optional[str] = None

@app.post("/chat/{agent_id}/message", dependencies=[Depends(verify_api_key)])
def chat(agent_id: str, body: ChatMessage):
    agent = get_agent(agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    session_id = get_or_create_session(agent_id, body.session_id)
    reply = send_message(
        agent_arn=agent["agent_arn"],
        agent_id=agent_id,
        session_id=session_id,
        user_message=body.message,
        region=agent["region"]
    )
    return {
        "reply": reply,
        "session_id": session_id
    }

@app.get("/chat/{agent_id}/history", dependencies=[Depends(verify_api_key)])
def history(agent_id: str, session_id: str):
    return {"history": get_history(agent_id, session_id)}

@app.delete("/chat/{agent_id}/session", dependencies=[Depends(verify_api_key)])
def reset_session(agent_id: str, session_id: str):
    clear_session(agent_id, session_id)
    return {"status": "cleared"}

# --- After successful deploy, save to agent_store ---
# In your existing /workflows/{id}/deploy handler, after deployment succeeds, add:
#
# from agent_store import save_agent
# agent_record = save_agent(
#     name=deploy_request.deployment_name,
#     prompt=workflow["prompt"],
#     agent_arn=result["agentRuntimeArn"],
#     image_uri=result["imageUri"],
#     region=deploy_request.region,
#     tools=workflow["tools"]
# )
# return {**result, "agent_id": agent_record["agent_id"]}
```

---

## 4. `static/index.html` — React Chat + Build UI

Single-file React app. No build step needed — CDN imports only.
Save this as `static/index.html` in your project.

```html
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>AgentCore Builder</title>
  <script src="https://cdnjs.cloudflare.com/ajax/libs/react/18.2.0/umd/react.development.js"></script>
  <script src="https://cdnjs.cloudflare.com/ajax/libs/react-dom/18.2.0/umd/react-dom.development.js"></script>
  <script src="https://cdnjs.cloudflare.com/ajax/libs/babel-standalone/7.23.2/babel.min.js"></script>
  <style>
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
           background: #0f1117; color: #e2e8f0; height: 100vh; }
    .app { display: flex; height: 100vh; }
    .sidebar { width: 260px; background: #1a1d27; border-right: 1px solid #2d3148;
               display: flex; flex-direction: column; padding: 16px; gap: 8px; }
    .sidebar h2 { font-size: 14px; color: #6b7280; text-transform: uppercase;
                  letter-spacing: 1px; margin-bottom: 8px; }
    .agent-item { padding: 10px 12px; border-radius: 8px; cursor: pointer;
                  border: 1px solid transparent; transition: all 0.15s; }
    .agent-item:hover { background: #2d3148; }
    .agent-item.active { background: #2d3148; border-color: #6366f1; }
    .agent-item .agent-name { font-size: 14px; font-weight: 500; }
    .agent-item .agent-status { font-size: 11px; color: #10b981; margin-top: 2px; }
    .main { flex: 1; display: flex; flex-direction: column; }
    .topbar { padding: 16px 24px; border-bottom: 1px solid #2d3148;
              display: flex; align-items: center; gap: 12px; }
    .topbar h1 { font-size: 16px; font-weight: 600; }
    .tab-btn { padding: 6px 16px; border-radius: 6px; border: none; cursor: pointer;
               font-size: 13px; background: transparent; color: #9ca3af; }
    .tab-btn.active { background: #6366f1; color: white; }
    .content { flex: 1; overflow: hidden; display: flex; flex-direction: column; }

    /* Chat */
    .chat-area { flex: 1; overflow-y: auto; padding: 24px; display: flex;
                 flex-direction: column; gap: 16px; }
    .message { max-width: 75%; padding: 12px 16px; border-radius: 12px;
               font-size: 14px; line-height: 1.6; white-space: pre-wrap; }
    .message.user { background: #6366f1; align-self: flex-end; border-radius: 12px 12px 2px 12px; }
    .message.assistant { background: #1e2235; align-self: flex-start;
                         border-radius: 12px 12px 12px 2px; border: 1px solid #2d3148; }
    .message.system { background: transparent; color: #6b7280; font-size: 12px;
                      align-self: center; }
    .chat-input-area { padding: 16px 24px; border-top: 1px solid #2d3148;
                       display: flex; gap: 8px; }
    .chat-input { flex: 1; padding: 12px 16px; background: #1e2235; border: 1px solid #2d3148;
                  border-radius: 10px; color: #e2e8f0; font-size: 14px; resize: none;
                  outline: none; }
    .chat-input:focus { border-color: #6366f1; }
    .send-btn { padding: 0 20px; background: #6366f1; border: none; border-radius: 10px;
                color: white; cursor: pointer; font-size: 14px; font-weight: 500; }
    .send-btn:disabled { opacity: 0.4; cursor: not-allowed; }
    .new-chat-btn { padding: 6px 12px; background: transparent; border: 1px solid #2d3148;
                    border-radius: 6px; color: #9ca3af; cursor: pointer; font-size: 12px; }

    /* Build */
    .build-area { flex: 1; overflow-y: auto; padding: 32px; }
    .build-area h2 { font-size: 20px; font-weight: 600; margin-bottom: 24px; }
    .form-group { margin-bottom: 20px; }
    .form-group label { display: block; font-size: 13px; color: #9ca3af;
                        margin-bottom: 8px; }
    .form-group textarea, .form-group input, .form-group select {
      width: 100%; padding: 12px 16px; background: #1e2235; border: 1px solid #2d3148;
      border-radius: 10px; color: #e2e8f0; font-size: 14px; outline: none; }
    .form-group textarea:focus, .form-group input:focus { border-color: #6366f1; }
    .form-group textarea { min-height: 120px; resize: vertical; }
    .tools-grid { display: flex; flex-wrap: wrap; gap: 8px; }
    .tool-chip { padding: 6px 14px; border-radius: 20px; border: 1px solid #2d3148;
                 cursor: pointer; font-size: 13px; color: #9ca3af; transition: all 0.15s; }
    .tool-chip.selected { background: #6366f1; border-color: #6366f1; color: white; }
    .deploy-btn { width: 100%; padding: 14px; background: #6366f1; border: none;
                  border-radius: 10px; color: white; font-size: 15px; font-weight: 600;
                  cursor: pointer; margin-top: 8px; }
    .deploy-btn:disabled { opacity: 0.4; cursor: not-allowed; }
    .status-box { padding: 16px; background: #1e2235; border-radius: 10px;
                  border: 1px solid #2d3148; margin-top: 20px; font-size: 13px;
                  line-height: 1.8; }
    .status-box.success { border-color: #10b981; }
    .status-box.error { border-color: #ef4444; }
    .label { color: #6b7280; }
    .val { color: #e2e8f0; }
    .val.green { color: #10b981; }
    .empty-state { flex: 1; display: flex; flex-direction: column; align-items: center;
                   justify-content: center; gap: 12px; color: #4b5563; }
    .spinner { display: inline-block; width: 16px; height: 16px; border: 2px solid #6366f1;
               border-top-color: transparent; border-radius: 50%; animation: spin 0.7s linear infinite; }
    @keyframes spin { to { transform: rotate(360deg); } }
  </style>
</head>
<body>
<div id="root"></div>
<script type="text/babel">
const { useState, useEffect, useRef } = React;

const API_KEY = "dev-key-change-in-production"; // match APP_API_KEY env var
const BASE = "";  // same origin — FastAPI serves this file

const api = async (path, options = {}) => {
  const res = await fetch(BASE + path, {
    ...options,
    headers: { "Content-Type": "application/json", "X-API-Key": API_KEY,
               ...(options.headers || {}) }
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
};

const AVAILABLE_TOOLS = [
  "web-search", "aws-kb-server", "aws-pricing",
  "aws-compliance-checker", "aws-performance-analyzer"
];

function BuildPage({ onAgentDeployed }) {
  const [prompt, setPrompt] = useState("");
  const [name, setName] = useState("");
  const [tools, setTools] = useState([]);
  const [deployConfig, setDeployConfig] = useState({
    region: "us-east-1",
    account_id: "",
    role_arn: ""
  });
  const [status, setStatus] = useState(null); // null | "generating" | "deploying" | "done" | "error"
  const [result, setResult] = useState(null);

  const toggleTool = (t) =>
    setTools(prev => prev.includes(t) ? prev.filter(x => x !== t) : [...prev, t]);

  const handleDeploy = async () => {
    if (!prompt || !name) return;
    setStatus("generating");
    setResult(null);
    try {
      // Step 1: Generate
      const gen = await api("/workflows/generate", {
        method: "POST",
        body: JSON.stringify({ prompt, tools })
      });
      setStatus("deploying");

      // Step 2: Deploy
      const dep = await api(`/workflows/${gen.workflow_id}/deploy`, {
        method: "POST",
        body: JSON.stringify({
          deployment_name: name,
          ...deployConfig
        })
      });
      setStatus("done");
      setResult({ ...gen, ...dep });
      onAgentDeployed();
    } catch (e) {
      setStatus("error");
      setResult({ error: e.message });
    }
  };

  return (
    <div className="build-area">
      <h2>Build & Deploy a New Agent</h2>

      <div className="form-group">
        <label>Agent Name</label>
        <input value={name} onChange={e => setName(e.target.value)}
               placeholder="e.g. aws-architecture-advisor" />
      </div>

      <div className="form-group">
        <label>Describe what this agent should do</label>
        <textarea value={prompt} onChange={e => setPrompt(e.target.value)}
          placeholder="e.g. Create an agent that answers AWS architecture questions, suggests services, and estimates costs..." />
      </div>

      <div className="form-group">
        <label>Tools (optional)</label>
        <div className="tools-grid">
          {AVAILABLE_TOOLS.map(t => (
            <span key={t} className={`tool-chip ${tools.includes(t) ? "selected" : ""}`}
                  onClick={() => toggleTool(t)}>{t}</span>
          ))}
        </div>
      </div>

      <div className="form-group">
        <label>AWS Region</label>
        <input value={deployConfig.region}
               onChange={e => setDeployConfig(p => ({...p, region: e.target.value}))} />
      </div>
      <div className="form-group">
        <label>AWS Account ID</label>
        <input value={deployConfig.account_id}
               onChange={e => setDeployConfig(p => ({...p, account_id: e.target.value}))}
               placeholder="123456789012" />
      </div>
      <div className="form-group">
        <label>Execution Role ARN</label>
        <input value={deployConfig.role_arn}
               onChange={e => setDeployConfig(p => ({...p, role_arn: e.target.value}))}
               placeholder="arn:aws:iam::123456789012:role/AgentCoreExecutionRole" />
      </div>

      <button className="deploy-btn"
              disabled={!prompt || !name || status === "generating" || status === "deploying"}
              onClick={handleDeploy}>
        {status === "generating" && <><span className="spinner" style={{marginRight:8}}/> Generating agent code...</>}
        {status === "deploying" && <><span className="spinner" style={{marginRight:8}}/> Deploying to AgentCore...</>}
        {(!status || status === "done" || status === "error") && "Generate & Deploy Agent"}
      </button>

      {result && (
        <div className={`status-box ${status === "done" ? "success" : "error"}`}>
          {status === "done" ? <>
            <div><span className="label">Status: </span><span className="val green">✓ Deployed</span></div>
            <div><span className="label">Agent ID: </span><span className="val">{result.agent_id}</span></div>
            <div><span className="label">ARN: </span><span className="val" style={{fontSize:11}}>{result.agentRuntimeArn}</span></div>
            <div><span className="label">Image: </span><span className="val" style={{fontSize:11}}>{result.imageUri}</span></div>
            <div style={{marginTop:8}}>→ Switch to <b>Chat</b> tab and select this agent to start talking to it.</div>
          </> : <>
            <div style={{color:"#ef4444"}}>Deploy failed</div>
            <div style={{fontSize:12, marginTop:8}}>{result.error}</div>
          </>}
        </div>
      )}
    </div>
  );
}

function ChatPage({ agents }) {
  const [selectedAgent, setSelectedAgent] = useState(null);
  const [sessionId, setSessionId] = useState(null);
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const bottomRef = useRef(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  const selectAgent = (agent) => {
    setSelectedAgent(agent);
    setSessionId(null);
    setMessages([{
      role: "system",
      content: `Connected to "${agent.name}". Start chatting below.`
    }]);
  };

  const sendMessage = async () => {
    if (!input.trim() || !selectedAgent || loading) return;
    const userMsg = input.trim();
    setInput("");
    setMessages(prev => [...prev, { role: "user", content: userMsg }]);
    setLoading(true);
    try {
      const res = await api(`/chat/${selectedAgent.agent_id}/message`, {
        method: "POST",
        body: JSON.stringify({ message: userMsg, session_id: sessionId })
      });
      setSessionId(res.session_id);
      setMessages(prev => [...prev, { role: "assistant", content: res.reply }]);
    } catch (e) {
      setMessages(prev => [...prev, {
        role: "system", content: `Error: ${e.message}`
      }]);
    }
    setLoading(false);
  };

  const newChat = () => {
    setSessionId(null);
    setMessages([{
      role: "system",
      content: `New conversation started with "${selectedAgent?.name}".`
    }]);
  };

  const handleKeyDown = (e) => {
    if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); sendMessage(); }
  };

  return (
    <div style={{display:"flex", flex:1, overflow:"hidden"}}>
      {/* Agent selector sidebar */}
      <div style={{width:220, borderRight:"1px solid #2d3148", padding:16, overflowY:"auto"}}>
        <div style={{fontSize:12, color:"#6b7280", marginBottom:12, textTransform:"uppercase",
                     letterSpacing:1}}>Deployed Agents</div>
        {agents.length === 0 && (
          <div style={{fontSize:13, color:"#4b5563"}}>
            No agents yet. Build one first.
          </div>
        )}
        {agents.map(a => (
          <div key={a.agent_id}
               className={`agent-item ${selectedAgent?.agent_id === a.agent_id ? "active" : ""}`}
               onClick={() => selectAgent(a)}>
            <div className="agent-name">{a.name}</div>
            <div className="agent-status">● {a.status}</div>
          </div>
        ))}
      </div>

      {/* Chat area */}
      <div style={{flex:1, display:"flex", flexDirection:"column"}}>
        {!selectedAgent ? (
          <div className="empty-state">
            <div style={{fontSize:32}}>💬</div>
            <div>Select an agent to start chatting</div>
          </div>
        ) : <>
          <div style={{padding:"12px 24px", borderBottom:"1px solid #2d3148",
                       display:"flex", justifyContent:"space-between", alignItems:"center"}}>
            <span style={{fontWeight:600}}>{selectedAgent.name}</span>
            <button className="new-chat-btn" onClick={newChat}>+ New Chat</button>
          </div>
          <div className="chat-area">
            {messages.map((m, i) => (
              <div key={i} className={`message ${m.role}`}>{m.content}</div>
            ))}
            {loading && (
              <div className="message assistant">
                <span className="spinner" />
              </div>
            )}
            <div ref={bottomRef} />
          </div>
          <div className="chat-input-area">
            <textarea className="chat-input" rows={2} value={input}
              onChange={e => setInput(e.target.value)} onKeyDown={handleKeyDown}
              placeholder="Type a message... (Enter to send, Shift+Enter for newline)" />
            <button className="send-btn" onClick={sendMessage}
                    disabled={!input.trim() || loading}>Send</button>
          </div>
        </>}
      </div>
    </div>
  );
}

function App() {
  const [tab, setTab] = useState("chat");
  const [agents, setAgents] = useState([]);

  const loadAgents = async () => {
    try {
      const data = await api("/agents");
      setAgents(data.agents || []);
    } catch (e) { console.error(e); }
  };

  useEffect(() => { loadAgents(); }, []);

  return (
    <div className="app">
      <div className="main">
        <div className="topbar">
          <h1>🤖 AgentCore Builder</h1>
          <button className={`tab-btn ${tab === "build" ? "active" : ""}`}
                  onClick={() => setTab("build")}>Build</button>
          <button className={`tab-btn ${tab === "chat" ? "active" : ""}`}
                  onClick={() => setTab("chat")}>Chat</button>
        </div>
        <div className="content">
          {tab === "build"
            ? <BuildPage onAgentDeployed={loadAgents} />
            : <ChatPage agents={agents} />}
        </div>
      </div>
    </div>
  );
}

ReactDOM.createRoot(document.getElementById("root")).render(<App />);
</script>
</body>
</html>
```

---

## 5. Making It Publicly Accessible (Deploy the FastAPI App)

Once your FastAPI + static UI is working locally, deploy it so others can access it.

### Quickest option — Docker + ECS Fargate

**Dockerfile for your FastAPI app:**
```dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
EXPOSE 8000
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
```

**requirements.txt additions:**
```
anthropic>=0.40.0
bedrock-agentcore>=0.1.0
boto3>=1.39.8
fastapi>=0.104.0
uvicorn>=0.24.0
python-multipart>=0.0.6
```

**Deploy to ECS (one-time setup):**
```bash
# Build and push your FastAPI app image
aws ecr create-repository --repository-name agentcore-builder-api
docker build -t agentcore-builder-api .
docker tag agentcore-builder-api:latest \
  123456789012.dkr.ecr.us-east-1.amazonaws.com/agentcore-builder-api:latest
docker push 123456789012.dkr.ecr.us-east-1.amazonaws.com/agentcore-builder-api:latest

# Then create ECS Fargate service via console or CDK
# Result: http://your-ecs-alb-url.us-east-1.elb.amazonaws.com
# Share that URL + your API key with anyone you want to give access
```

---

## 6. Updated `.env` File

```bash
# Anthropic
ANTHROPIC_API_KEY=sk-ant-...

# AWS
AWS_REGION=us-east-1
AWS_ACCOUNT_ID=677276078734
AGENTCORE_EXECUTION_ROLE_ARN=arn:aws:iam::677276078734:role/AgentCoreExecutionRole

# App access control
APP_API_KEY=your-strong-api-key-here
```

---

## 7. Updated API Endpoints (Full List)

```
# Build
POST   /workflows/generate              → generate agent code from prompt
GET    /workflows/{id}                  → get workflow + generated code
PUT    /workflows/{id}/agents           → edit agent (regenerate code)
POST   /workflows/{id}/tools            → add tool
DELETE /workflows/{id}/tools            → remove tool
GET    /tools/available                 → list available tools
POST   /workflows/{id}/deploy           → deploy to AgentCore Runtime
GET    /deployments/{id}                → deployment status + ARN

# Agents
GET    /agents                          → list all deployed agents

# Chat (the new ones)
POST   /chat/{agent_id}/message         → send message, get reply + session_id
GET    /chat/{agent_id}/history         → get full conversation history
DELETE /chat/{agent_id}/session         → clear/reset conversation

# System
GET    /health                          → health check
GET    /                                → serves the React UI
```

---

## How the Full Flow Works End-to-End

```
1. You/anyone opens  http://your-app-url/
   → React UI loads (Build + Chat tabs)

2. Build tab:
   → Type a prompt describing the agent
   → Select tools
   → Click "Generate & Deploy"
   → FastAPI generates agent_handler.py using Claude
   → Builds Docker image, pushes to ECR
   → Calls create_agent_runtime → agent appears in AWS console
   → agent_id returned to UI

3. Chat tab:
   → Agent appears in sidebar
   → Click agent → type message → Enter
   → FastAPI calls invoke_agent_runtime(ARN, session_id, payload)
   → Response streams back and appears in chat
   → Same session_id reused for conversation memory
   → "New Chat" button resets session

4. Share access:
   → Give someone your app URL + API key
   → They can chat with any deployed agent
   → Or deploy their own agents via the Build tab
```

---

## What Changed From V2

| Item | V2 | V3 (This Document) |
|---|---|---|
| Chat UI | None | React chat interface in browser |
| Agent listing | None | GET /agents endpoint + sidebar |
| Public access | Not addressed | FastAPI serves UI + API Key auth |
| Conversation memory | Not addressed | Session-based history in chat_manager |
| New session | Not addressed | "New Chat" button resets session_id |
| Deployment feedback | curl only | Live status in Build tab UI |
| Share with others | No path | App URL + API key |

---

## Status Summary

| Feature | Status |
|---|---|
| Prompt → agent code generation | ✅ |
| ECR build + push | ✅ |
| AgentCore Runtime deployment | ✅ |
| Agent appears in AWS console | ✅ |
| Chat UI in browser | ✅ V3 |
| Conversation history per session | ✅ V3 |
| Public URL for sharing | ✅ V3 (ECS deploy) |
| API key access control | ✅ V3 |
| Persistent DB storage | 🟡 Replace dicts with DynamoDB later |
| Streaming responses in UI | 🟡 Currently full response — add SSE later |
