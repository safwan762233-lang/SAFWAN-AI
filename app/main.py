from typing import Optional
from fastapi import FastAPI, HTTPException, Header
from fastapi.responses import HTMLResponse, PlainTextResponse
from pydantic import BaseModel, Field
from .config import SAFWAN_APP_TOKEN, OLLAMA_MODEL, OLLAMA_BASE_URL
from .db import connect, init_db
from .ollama import chat, list_models, OllamaError

app = FastAPI(title="SAFWAN AI", version="0.1.0")

@app.on_event("startup")
def startup():
    init_db()

def authorize(authorization: Optional[str]):
    if SAFWAN_APP_TOKEN and authorization != f"Bearer {SAFWAN_APP_TOKEN}":
        raise HTTPException(401, "Unauthorized")

class ChatInput(BaseModel):
    message: str = Field(min_length=1, max_length=12000)
    conversation_id: Optional[int] = None
    model: Optional[str] = None

@app.get("/", response_class=HTMLResponse)
def home():
    return HTML

@app.get("/api/health")
async def health():
    try:
        models = await list_models()
        return {"app":"SAFWAN AI","status":"ok","ollama":"connected","models":models,"default_model":OLLAMA_MODEL}
    except OllamaError as exc:
        return {"app":"SAFWAN AI","status":"degraded","ollama":"disconnected","detail":str(exc),"configured_url":OLLAMA_BASE_URL}

@app.get("/api/conversations")
def conversations(authorization: Optional[str] = Header(default=None)):
    authorize(authorization)
    with connect() as con:
        rows = con.execute("SELECT id,title,created_at,updated_at FROM conversations ORDER BY updated_at DESC LIMIT 100").fetchall()
        return [dict(row) for row in rows]

@app.get("/api/conversations/{cid}")
def get_conversation(cid: int, authorization: Optional[str] = Header(default=None)):
    authorize(authorization)
    with connect() as con:
        conv = con.execute("SELECT * FROM conversations WHERE id=?", (cid,)).fetchone()
        if not conv:
            raise HTTPException(404, "Conversation not found")
        msgs = con.execute("SELECT role,content,created_at FROM messages WHERE conversation_id=? ORDER BY id", (cid,)).fetchall()
        return {"conversation":dict(conv),"messages":[dict(m) for m in msgs]}

@app.post("/api/chat")
async def send_chat(body: ChatInput, authorization: Optional[str] = Header(default=None)):
    authorize(authorization)
    with connect() as con:
        cid = body.conversation_id
        if cid is None:
            title = body.message.replace("\\n", " ")[:60] or "New conversation"
            cur = con.execute("INSERT INTO conversations(title) VALUES(?)", (title,))
            cid = cur.lastrowid
        elif not con.execute("SELECT id FROM conversations WHERE id=?", (cid,)).fetchone():
            raise HTTPException(404, "Conversation not found")
        con.execute("INSERT INTO messages(conversation_id,role,content) VALUES(?,?,?)", (cid,"user",body.message))
        rows = con.execute("SELECT role,content FROM messages WHERE conversation_id=? ORDER BY id DESC LIMIT 20", (cid,)).fetchall()
        history = [{"role":r["role"],"content":r["content"]} for r in reversed(rows)]
    try:
        answer, used_model = await chat(history, body.model)
    except OllamaError as exc:
        raise HTTPException(503, str(exc))
    with connect() as con:
        con.execute("INSERT INTO messages(conversation_id,role,content) VALUES(?,?,?)", (cid,"assistant",answer))
        con.execute("UPDATE conversations SET updated_at=CURRENT_TIMESTAMP WHERE id=?", (cid,))
    return {"conversation_id":cid,"answer":answer,"model":used_model}

@app.get("/api/models")
async def models(authorization: Optional[str] = Header(default=None)):
    authorize(authorization)
    try:
        return {"models":await list_models(),"default":OLLAMA_MODEL}
    except OllamaError as exc:
        raise HTTPException(503, str(exc))

@app.get("/api/conversations/{cid}/export", response_class=PlainTextResponse)
def export_conversation(cid: int, authorization: Optional[str] = Header(default=None)):
    authorize(authorization)
    with connect() as con:
        conv = con.execute("SELECT title FROM conversations WHERE id=?", (cid,)).fetchone()
        if not conv:
            raise HTTPException(404, "Conversation not found")
        msgs = con.execute("SELECT role,content FROM messages WHERE conversation_id=? ORDER BY id", (cid,)).fetchall()
    lines = [f"# {conv['title']}", ""]
    for msg in msgs:
        lines += [f"## {msg['role']}", "", msg["content"], ""]
    return "\\n".join(lines)

HTML = """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>SAFWAN AI</title><style>
:root{color-scheme:dark;--bg:#0b1020;--panel:#111a2e;--line:#263653;--text:#edf3ff;--muted:#91a3bf;--cyan:#39d5d0}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--text);font:15px system-ui,Segoe UI,sans-serif;height:100vh}
.shell{display:grid;grid-template-columns:260px 1fr;height:100vh}.side{background:#080e1b;border-right:1px solid var(--line);padding:18px;display:flex;flex-direction:column;gap:14px}
.brand{font-size:25px;font-weight:800}.brand span{color:var(--cyan)}.muted{color:var(--muted);font-size:12px}
button{border:1px solid var(--line);background:#17243b;color:var(--text);border-radius:12px;padding:11px 14px;cursor:pointer}.primary{background:linear-gradient(100deg,#087f91,#5548c9);border:0;font-weight:700}
#history{overflow:auto;display:flex;flex-direction:column;gap:7px}.historyItem{text-align:left;background:transparent;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.main{display:flex;flex-direction:column;min-width:0}.top{height:66px;border-bottom:1px solid var(--line);display:flex;align-items:center;justify-content:space-between;padding:0 24px}
#messages{flex:1;overflow:auto;padding:26px max(16px,calc((100% - 850px)/2));display:flex;flex-direction:column;gap:18px}
.welcome{margin:auto;max-width:680px;text-align:center}.welcome h1{font-size:38px;margin:0 0 12px}.welcome p{color:var(--muted);line-height:1.7}
.msg{max-width:850px;width:100%;margin:auto;display:flex;gap:12px;line-height:1.65;white-space:pre-wrap;overflow-wrap:anywhere}.avatar{width:34px;height:34px;border-radius:11px;display:grid;place-items:center;background:#17243b;flex-shrink:0;color:var(--cyan);font-weight:800}.bubble{padding:13px 16px;border:1px solid var(--line);border-radius:15px;background:var(--panel);width:100%}
.composerWrap{padding:14px 18px 20px;border-top:1px solid var(--line)}.composer{max-width:850px;margin:auto;border:1px solid var(--line);background:var(--panel);border-radius:18px;padding:10px;display:flex;gap:8px;align-items:end}
textarea{flex:1;resize:vertical;min-height:52px;max-height:180px;background:transparent;border:0;outline:0;color:var(--text);font:inherit;padding:10px}.foot{max-width:850px;margin:8px auto 0;color:var(--muted);font-size:11px;text-align:center}
@media(max-width:700px){.shell{grid-template-columns:1fr}.side{display:none}.top{padding:0 14px}#messages{padding:18px 12px}.welcome h1{font-size:29px}}
</style></head><body><div class="shell"><aside class="side"><div><div class="brand">SAFWAN <span>AI</span></div><div class="muted">PRIVATE BUSINESS WORKSPACE</div></div>
<button class="primary" onclick="newChat()">＋ New chat</button><div class="muted">RECENT CHATS</div><div id="history"></div><div class="muted" style="margin-top:auto">Local-first • Your model • Your data</div></aside>
<main class="main"><header class="top"><div><b>SAFWAN AI</b><div class="muted">Business assistant</div></div><div id="status" class="muted">Checking local AI…</div></header>
<section id="messages"><div class="welcome"><h1>What can we build today?</h1><p>Your private business assistant for planning, customer replies, operations, sales summaries and documents. Ask in বাংলা, Banglish or English.</p></div></section>
<div class="composerWrap"><div class="composer"><textarea id="prompt" placeholder="Message SAFWAN AI…" onkeydown="if(event.key==='Enter'&&!event.shiftKey){event.preventDefault();send()}"></textarea><button class="primary" onclick="send()">Send ↑</button></div><div class="foot">AI can make mistakes. Verify important business, legal and financial decisions.</div></div></main></div>
<script>
let cid=null;const $=x=>document.getElementById(x);
function add(role,text){let e=document.createElement('div');e.className='msg';let a=document.createElement('div');a.className='avatar';a.textContent=role==='user'?'YOU':'S';let b=document.createElement('div');b.className='bubble';b.textContent=text;e.append(a,b);$('messages').append(e);$('messages').scrollTop=$('messages').scrollHeight;return b}
function newChat(){cid=null;$('messages').innerHTML='<div class="welcome"><h1>What can we build today?</h1><p>Your private business assistant. Ask in বাংলা, Banglish or English.</p></div>'}
async function status(){try{let d=await(await fetch('/api/health')).json();$('status').textContent=d.ollama==='connected'?'● Local AI connected':'● Ollama not connected';$('status').style.color=d.ollama==='connected'?'#39d5a0':'#ffb86b'}catch{$('status').textContent='Status unavailable'}}
async function history(){try{let xs=await(await fetch('/api/conversations')).json();$('history').innerHTML='';xs.forEach(x=>{let b=document.createElement('button');b.className='historyItem';b.textContent=x.title;b.onclick=()=>load(x.id);$('history').append(b)})}catch{}}
async function load(id){let d=await(await fetch('/api/conversations/'+id)).json();cid=id;$('messages').innerHTML='';d.messages.forEach(m=>add(m.role,m.content))}
async function send(){let t=$('prompt').value.trim();if(!t)return;$('prompt').value='';add('user',t);let p=add('assistant','Thinking…');try{let r=await fetch('/api/chat',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({message:t,conversation_id:cid})});let d=await r.json();if(!r.ok)throw Error(d.detail||'Request failed');cid=d.conversation_id;p.textContent=d.answer;history()}catch(e){p.textContent='Error: '+e.message+'\\nCheck Ollama is running and a model is downloaded.'}}
status();history();
</script></body></html>"""
