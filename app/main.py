from typing import Optional
from fastapi import FastAPI, HTTPException, Header
from fastapi.responses import HTMLResponse, PlainTextResponse
from pydantic import BaseModel, Field
from .config import SAFWAN_APP_TOKEN, OLLAMA_MODEL, OLLAMA_BASE_URL
from .db import connect, init_db
from .ollama import chat, list_models, OllamaError
from .business import router as business_router, get_business_context_data
from .api_v1 import router as api_v1_router
from .knowledge import router as knowledge_router, search_knowledge
from .memory import router as memory_router, remember
from .intelligence import build_intelligence_context
from .model_router import get_model_usage
from .evaluation import router as evaluation_router
from .config import SAFWAN_CODING_MODEL, SAFWAN_REASONING_MODEL, SAFWAN_FALLBACK_MODEL

app = FastAPI(title="SAFWAN AI", version="0.2.0")
app.include_router(business_router)
app.include_router(api_v1_router)
app.include_router(knowledge_router)
app.include_router(memory_router)
app.include_router(evaluation_router)

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
    remember(body.message, source_conversation_id=cid)
    try:
        context = build_intelligence_context(body.message)
        answer, used_model = await chat(history, body.model, context)
    except OllamaError as exc:
        raise HTTPException(503, str(exc))
    with connect() as con:
        con.execute("INSERT INTO messages(conversation_id,role,content) VALUES(?,?,?)", (cid,"assistant",answer))
        con.execute("UPDATE conversations SET updated_at=CURRENT_TIMESTAMP WHERE id=?", (cid,))
    return {"conversation_id":cid,"answer":answer,"model":used_model}

@app.get("/api/model-router/status")
async def model_router_status(authorization: Optional[str] = Header(default=None)):
    authorize(authorization)
    try:
        installed = await list_models()
    except OllamaError as exc:
        raise HTTPException(503, str(exc))
    return {
        "installed_models": installed,
        "default_model": OLLAMA_MODEL,
        "preferences": {
            "coding": SAFWAN_CODING_MODEL,
            "reasoning": SAFWAN_REASONING_MODEL,
            "fallback": SAFWAN_FALLBACK_MODEL or None,
        },
        "usage": get_model_usage(),
        "routing_note": "Specialist preferences are used only when the model is installed; otherwise the default installed model is selected.",
    }

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
<button class="primary" onclick="newChat()">＋ New chat</button><button onclick="showChat()">AI Chat</button><button onclick="showDashboard()">▦ Business Dashboard</button><button onclick="showApiManagement()">⚿ API Management</button><button onclick="showKnowledge()">▤ Knowledge Base</button><button onclick="showMemory()">◉ Long-term Memory</button><div class="muted">RECENT CHATS</div><div id="history"></div><div class="muted" style="margin-top:auto">Local-first • Your model • Your data</div></aside>
<main class="main"><header class="top"><div><b>SAFWAN AI</b><div class="muted">Business assistant</div></div><div id="status" class="muted">Checking local AI…</div></header>
<section id="dashboard" style="display:none;flex:1;overflow:auto;padding:24px"><div style="max-width:1100px;margin:auto"><h2>Business Workspace</h2><p class="muted">Manage customers, inventory and sales from one place.</p><div id="dashCards" style="display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:12px"></div><div style="display:flex;gap:8px;flex-wrap:wrap;margin:20px 0"><button onclick="showBizTab('overview')">Overview</button><button onclick="showBizTab('customers')">Customers</button><button onclick="showBizTab('products')">Products / Inventory</button><button onclick="showBizTab('sales')">Sales</button></div><div id="bizPanel" class="bubble">Loading business data…</div><div style="margin-top:14px"><button onclick="loadDashboard()">↻ Refresh</button></div></div></section><section id="apiManagement" style="display:none;flex:1;overflow:auto;padding:24px"><div style="max-width:1050px;margin:auto"><h2>SAFWAN API Management</h2><p class="muted">Manage API keys and monitor usage. Your master token stays in this browser tab only.</p><div class="bubble" style="display:grid;gap:10px;margin:16px 0"><label for="apiAdminToken">Master Token</label><input id="apiAdminToken" type="password" autocomplete="off" placeholder="Enter SAFWAN_APP_TOKEN"><div style="display:flex;gap:8px;flex-wrap:wrap"><button class="primary" onclick="connectApiAdmin()">Connect</button><button onclick="disconnectApiAdmin()">Disconnect</button></div><div id="apiAdminStatus" class="muted">Not connected</div></div><div id="apiKeyCreatePanel" class="bubble" style="display:none;margin:12px 0"><h3>Create API Key</h3><form onsubmit="createManagedKey(event)" style="display:flex;gap:8px;flex-wrap:wrap"><input name="name" required minlength="2" maxlength="80" placeholder="Integration name" style="flex:1;min-width:180px"><button class="primary">Create key</button></form><p id="newApiKey" style="overflow-wrap:anywhere"></p></div><div id="apiKeyList" class="bubble" style="display:none;margin:12px 0">Connect with master token to view API keys.</div><div id="apiUsagePanel" class="bubble" style="display:none;margin:12px 0"><h3>API Usage</h3><div style="display:flex;gap:8px;align-items:center;flex-wrap:wrap"><label for="usageHours">Period</label><select id="usageHours"><option value="24">24 hours</option><option value="168">7 days</option><option value="720">30 days</option></select><button onclick="loadApiUsage()">Refresh usage</button></div><div id="apiUsageData" style="margin-top:12px"></div></div></div></section><section id="knowledge" style="display:none;flex:1;overflow:auto;padding:24px"><div style="max-width:1050px;margin:auto"><h2>Local Knowledge Base</h2><p class="muted">Upload TXT, Markdown, PDF or DOCX files. SAFWAN AI will search their text when answering your questions.</p><div class="bubble" style="display:grid;gap:10px;margin:16px 0"><p id="knowledgeAuth" class="muted">Connect with your master token in API Management first.</p><form onsubmit="uploadKnowledge(event)" style="display:flex;gap:8px;flex-wrap:wrap"><input id="knowledgeFile" type="file" accept=".txt,.md,.pdf,.docx" required><button class="primary">Upload document</button></form><p class="muted">Maximum file size: 10 MB. Scanned PDFs without selectable text may not be readable.</p><div id="knowledgeStatus" class="muted"></div></div><div class="bubble"><div style="display:flex;justify-content:space-between;align-items:center;gap:10px;flex-wrap:wrap"><h3>Uploaded documents</h3><div style="display:flex;gap:8px"><button onclick="reindexKnowledge()">Reindex old files</button><button onclick="loadKnowledgeDocs()">Refresh</button></div></div><div id="knowledgeDocs">Connect with master token to list documents.</div></div><div class="bubble" style="margin-top:14px"><h3>Test document search</h3><form onsubmit="testKnowledgeSearch(event)" style="display:flex;gap:8px;flex-wrap:wrap"><input name="query" required placeholder="Ask something from your documents" style="flex:1;min-width:180px"><button>Search</button></form><div id="knowledgeResults"></div></div></div></section><section id="memory" style="display:none;flex:1;overflow:auto;padding:24px"><div style="max-width:1050px;margin:auto"><h2>SAFWAN Long-term Memory</h2><p class="muted">Conversation memories are saved locally in this shared workspace. Review and delete anything you do not want retained.</p><div class="bubble" style="display:grid;gap:10px;margin:16px 0"><form onsubmit="addMemoryItem(event)" style="display:grid;gap:8px"><textarea name="content" required minlength="5" maxlength="4000" placeholder="Add a fact SAFWAN should remember…"></textarea><input name="category" maxlength="40" value="preference" placeholder="Category (e.g. preference, goal, project)"><button class="primary">Save memory</button></form><div id="memoryStatus" class="muted"></div></div><div class="bubble"><div style="display:flex;justify-content:space-between;align-items:center;gap:8px;flex-wrap:wrap"><h3>Saved memories</h3><div style="display:flex;gap:8px"><button onclick="loadMemories()">Refresh</button><button onclick="clearMemories()">Clear all</button></div></div><div id="memoryItems">Connect with master token in API Management to view memories.</div></div><div class="bubble" style="margin-top:14px"><h3>Search memories</h3><form onsubmit="searchMemoryItems(event)" style="display:flex;gap:8px;flex-wrap:wrap"><input name="query" required placeholder="Search what SAFWAN remembers" style="flex:1;min-width:180px"><button>Search</button></form><div id="memorySearchResults"></div></div></div></section><section id="messages"><div class="welcome"><h1>What can we build today?</h1><p>Your private business assistant for planning, customer replies, operations, sales summaries and documents. Ask in বাংলা, Banglish or English.</p></div></section>
<div class="composerWrap"><div class="composer"><textarea id="prompt" placeholder="Message SAFWAN AI…" onkeydown="if(event.key==='Enter'&&!event.shiftKey){event.preventDefault();send()}"></textarea><button class="primary" onclick="send()">Send ↑</button></div><div class="foot">AI can make mistakes. Verify important business, legal and financial decisions.</div></div></main></div>
<script>
let cid=null;let apiAdminToken='';const $=x=>document.getElementById(x);
function showApiManagement(){$('dashboard').style.display='none';$('knowledge').style.display='none';$('memory').style.display='none';$('messages').style.display='none';$('apiManagement').style.display='block'}
function showKnowledge(){$('dashboard').style.display='none';$('apiManagement').style.display='none';$('memory').style.display='none';$('messages').style.display='none';$('knowledge').style.display='block';loadKnowledgeDocs()}
function showMemory(){$('dashboard').style.display='none';$('apiManagement').style.display='none';$('knowledge').style.display='none';$('messages').style.display='none';$('memory').style.display='block';loadMemories()}
function disconnectApiAdmin(){apiAdminToken='';$('apiAdminToken').value='';$('apiAdminStatus').textContent='Disconnected';$('apiKeyCreatePanel').style.display='none';$('apiKeyList').style.display='none';$('apiUsagePanel').style.display='none';$('newApiKey').textContent=''}
async function adminApi(path,opts={}){if(!apiAdminToken)throw Error('Enter the master token and connect first');let r=await fetch(path,{...opts,headers:{'Content-Type':'application/json','Authorization':'Bearer '+apiAdminToken,...(opts.headers||{})}});let d=await r.json();if(!r.ok)throw Error(d.detail||'Request failed');return d}
async function connectApiAdmin(){apiAdminToken=$('apiAdminToken').value.trim();try{await loadManagedKeys();$('apiAdminStatus').textContent='Connected to SAFWAN API administration';$('apiKeyCreatePanel').style.display='block';$('apiKeyList').style.display='block';$('apiUsagePanel').style.display='block';await loadApiUsage()}catch(e){apiAdminToken='';$('apiAdminStatus').textContent='Connection failed: '+e.message;}}
async function loadManagedKeys(){let xs=await adminApi('/api/keys');$('apiKeyList').innerHTML='<h3>API Keys</h3>'+ (xs.length?xs.map(x=>'<div style="border-top:1px solid var(--line);padding:12px 0"><b>'+esc(x.name)+'</b><div class="muted">'+esc(x.key_prefix)+' · Created '+esc(x.created_at)+' · '+(x.revoked_at?'Revoked':'Active')+'</div><div style="display:flex;gap:8px;flex-wrap:wrap;margin-top:8px">'+(!x.revoked_at?'<button onclick="renameManagedKey('+x.id+',\''+esc(x.name).replace(/\\'/g,'&#39;')+'\')">Rename</button><button onclick="revokeManagedKey('+x.id+')">Revoke</button>':'')+'</div></div>').join(''):'<p class="muted">No API keys created yet.</p>')}
async function createManagedKey(e){e.preventDefault();let name=new FormData(e.target).get('name');try{let d=await adminApi('/api/keys',{method:'POST',body:JSON.stringify({name})});$('newApiKey').textContent='Copy this key now (it will not be shown again): '+d.key;e.target.reset();await loadManagedKeys()}catch(x){alert(x.message)}}
async function renameManagedKey(id){let name=prompt('New API key name:');if(name===null)return;try{await adminApi('/api/keys/'+id,{method:'PATCH',body:JSON.stringify({name})});await loadManagedKeys()}catch(e){alert(e.message)}}
async function revokeManagedKey(id){if(!confirm('Revoke this API key? Existing integrations using it will stop working.'))return;try{await adminApi('/api/keys/'+id,{method:'DELETE'});await loadManagedKeys();await loadApiUsage()}catch(e){alert(e.message)}}
async function loadMemories(){if(!apiAdminToken){$('memoryItems').textContent='Connect with master token in API Management first.';return}try{let d=await adminApi('/api/memory');$('memoryItems').innerHTML=d.items.length?d.items.map(x=>'<div style="border-top:1px solid var(--line);padding:10px 0"><b>'+esc(x.category)+'</b><p style="white-space:pre-wrap">'+esc(x.content)+'</p><span class="muted">'+esc(x.created_at)+'</span><button style="margin-left:10px" onclick="deleteMemoryItem('+x.id+')">Delete</button></div>').join(''):'<p class="muted">No saved memories yet.</p>';$('memoryStatus').textContent=d.count+' saved memories · '+(d.enabled?'automatic memory enabled':'automatic memory disabled')}catch(e){$('memoryItems').textContent=e.message}}
async function addMemoryItem(e){e.preventDefault();try{let form=new FormData(e.target);let d=await adminApi('/api/memory',{method:'POST',body:JSON.stringify({content:form.get('content'),category:form.get('category')||'fact'})});$('memoryStatus').textContent='Memory saved · ID '+d.id;e.target.reset();await loadMemories()}catch(x){$('memoryStatus').textContent='Save error: '+x.message}}
async function deleteMemoryItem(id){if(!confirm('Delete this saved memory?'))return;try{await adminApi('/api/memory/'+id,{method:'DELETE'});await loadMemories()}catch(e){alert(e.message)}}
async function clearMemories(){if(!confirm('Permanently clear all saved memories?'))return;try{let d=await adminApi('/api/memory',{method:'DELETE'});$('memoryStatus').textContent=d.deleted+' memories deleted';await loadMemories()}catch(e){$('memoryStatus').textContent=e.message}}
async function searchMemoryItems(e){e.preventDefault();try{let query=new FormData(e.target).get('query');let d=await adminApi('/api/memory/search',{method:'POST',body:JSON.stringify({query})});$('memorySearchResults').innerHTML=d.results.length?d.results.map(x=>'<div style="border-top:1px solid var(--line);padding:10px 0"><b>'+esc(x.category)+'</b><p>'+esc(x.content)+'</p><span class="muted">Relevance '+x.score+'</span></div>').join(''):'<p class="muted">No related memories found.</p>'}catch(x){$('memorySearchResults').textContent=x.message}}
async function loadKnowledgeDocs(){if(!apiAdminToken){$('knowledgeDocs').textContent='Open API Management and connect with your master token first.';return}try{let xs=await adminApi('/api/knowledge/documents');$('knowledgeDocs').innerHTML=xs.length?xs.map(x=>'<div style="border-top:1px solid var(--line);padding:10px 0"><b>'+esc(x.filename)+'</b><div class="muted">'+esc(x.file_type.toUpperCase())+' · '+x.chunks+' chunks · '+(x.embedded_chunks||0)+' embedded · '+x.char_count+' characters · '+esc(x.created_at)+'</div><button style="margin-top:6px" onclick="deleteKnowledgeDoc('+x.id+')">Delete</button></div>').join(''):'<p class="muted">No documents uploaded.</p>';$('knowledgeAuth').textContent='Connected with master token.'}catch(e){$('knowledgeDocs').textContent=e.message}}
async function uploadKnowledge(e){e.preventDefault();if(!apiAdminToken){alert('Connect with master token in API Management first.');return}let file=$('knowledgeFile').files[0];if(!file)return;let form=new FormData();form.append('file',file);$('knowledgeStatus').textContent='Uploading and extracting text…';try{let r=await fetch('/api/knowledge/upload',{method:'POST',headers:{'Authorization':'Bearer '+apiAdminToken},body:form});let d=await r.json();if(!r.ok)throw Error(d.detail||'Upload failed');$('knowledgeStatus').textContent='Uploaded '+d.filename+' · '+d.chunks+' chunks · '+(d.embedded?'semantic index ready':'keyword fallback: '+(d.embedding_warning||'embedding model unavailable'));e.target.reset();await loadKnowledgeDocs()}catch(x){$('knowledgeStatus').textContent='Upload error: '+x.message}}
async function reindexKnowledge(){if(!apiAdminToken){alert('Connect with master token first.');return}$('knowledgeStatus').textContent='Creating local embeddings for older document chunks…';try{let d=await adminApi('/api/knowledge/reindex',{method:'POST'});$('knowledgeStatus').textContent='Reindex complete · '+d.indexed+' chunks indexed · '+d.remaining+' remaining';await loadKnowledgeDocs()}catch(e){$('knowledgeStatus').textContent='Reindex error: '+e.message}}
async function deleteKnowledgeDoc(id){if(!confirm('Delete this document and its indexed text?'))return;try{await adminApi('/api/knowledge/documents/'+id,{method:'DELETE'});await loadKnowledgeDocs()}catch(e){alert(e.message)}}
async function testKnowledgeSearch(e){e.preventDefault();if(!apiAdminToken){alert('Connect with master token first.');return}let query=new FormData(e.target).get('query');try{let d=await adminApi('/api/knowledge/search',{method:'POST',body:JSON.stringify({query})});$('knowledgeResults').innerHTML=d.results.length?d.results.map(x=>'<div style="border-top:1px solid var(--line);padding:10px 0"><b>'+esc(x.filename)+'</b><p style="white-space:pre-wrap">'+esc(x.content)+'</p><span class="muted">Search: '+esc(x.method)+' · semantic '+x.semantic_score+' · keyword '+x.keyword_score+'</span></div>').join(''):'<p class="muted">No matching document text found.</p>'}catch(x){$('knowledgeResults').textContent=x.message}}
async function loadApiUsage(){try{let d=await adminApi('/api/usage?hours='+$('usageHours').value);$('apiUsageData').innerHTML='<h3>Total requests: '+d.total_requests+'</h3><p class="muted">Limit: '+d.rate_limit_per_key_per_minute+' requests per API key / minute</p><h4>By API key</h4>'+(d.by_api_key.length?d.by_api_key.map(x=>'<p>'+esc(x.name)+' · '+x.requests+' requests · '+x.rate_limited+' rate limited</p>').join(''):'<p class="muted">No requests in this period.</p>')+'<h4>Recent requests</h4>'+(d.recent_requests.length?d.recent_requests.map(x=>'<p>'+esc(x.key_name)+' · '+esc(x.endpoint)+' · HTTP '+x.status_code+' · '+esc(x.created_at)+'</p>').join(''):'<p class="muted">No recent requests.</p>')}catch(e){$('apiUsageData').textContent='Usage report error: '+e.message}}

function add(role,text){let e=document.createElement('div');e.className='msg';let a=document.createElement('div');a.className='avatar';a.textContent=role==='user'?'YOU':'S';let b=document.createElement('div');b.className='bubble';b.textContent=text;e.append(a,b);$('messages').append(e);$('messages').scrollTop=$('messages').scrollHeight;return b}
function showChat(){$('dashboard').style.display='none';$('apiManagement').style.display='none';$('knowledge').style.display='none';$('memory').style.display='none';$('messages').style.display='flex'}
function showDashboard(){$('messages').style.display='none';$('apiManagement').style.display='none';$('knowledge').style.display='none';$('memory').style.display='none';$('dashboard').style.display='block';loadDashboard()}
async function loadDashboard(){try{let d=await(await fetch('/api/business/context')).json();if(!d||d.detail)throw Error(d.detail||'Could not load');let cards=[['Products',d.product_count],['Customers',d.customer_count],['Inventory value',Number(d.inventory_value).toLocaleString()],['Confirmed sales',d.confirmed_sales_count],['Sales total',Number(d.confirmed_sales_total).toLocaleString()],['Low stock',d.low_stock_count]];$('dashCards').innerHTML=cards.map(([k,v])=>`<div class="bubble"><div class="muted">${k}</div><div style="font-size:25px;font-weight:750;margin-top:8px">${v}</div></div>`).join('');$('lowStock').textContent=d.low_stock_products.length?d.low_stock_products.map(p=>`${p.name} (SKU ${p.sku}) — stock ${p.stock_qty}, alert at ${p.low_stock_at}`).join('\\n'):'No low-stock products';$('recentSales').textContent=d.recent_sales.length?d.recent_sales.map(s=>`${s.reference} • ${s.status} • ${s.total} • ${s.created_at}`).join('\\n'):'No sales yet'}catch(e){$('dashCards').textContent='Dashboard unavailable: '+e.message;$('lowStock').textContent='';$('recentSales').textContent=''}}
let bizTab='overview';
function esc(v){return String(v??'').replace(/[&<>"']/g,ch=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[ch]))}
function showBizTab(tab){bizTab=tab;renderBizTab()}
let bizCache={customers:[],products:[],sales:[]};
async function api(path,opts={}){let r=await fetch('/api/business/'+path,{...opts,headers:{'Content-Type':'application/json',...(apiAdminToken?{'Authorization':'Bearer '+apiAdminToken}:{}),...(opts.headers||{})}});let d=await r.json();if(!r.ok)throw Error(d.detail||'Request failed');return d}
async function loadDashboard(){try{let d=await api('context');let cards=[['Products',d.product_count],['Customers',d.customer_count],['Inventory value',Number(d.inventory_value).toLocaleString()],['Confirmed sales',d.confirmed_sales_count],['Sales total',Number(d.confirmed_sales_total).toLocaleString()],['Low stock',d.low_stock_count]];$('dashCards').innerHTML=cards.map(([k,v])=>`<div class="bubble"><div class="muted">${k}</div><div style="font-size:24px;font-weight:750;margin-top:8px">${v}</div></div>`).join('');bizCache.low=d.low_stock_products;bizCache.recent=d.recent_sales;await refreshBizLists();renderBizTab()}catch(e){$('bizPanel').textContent='Dashboard error: '+e.message}}
async function refreshBizLists(){[bizCache.customers,bizCache.products,bizCache.sales]=await Promise.all([api('customers'),api('products'),api('sales')])}
function renderBizTab(){let p=$('bizPanel');if(bizTab==='overview'){p.innerHTML='<h3>Low stock products</h3>'+(bizCache.low?.length?bizCache.low.map(x=>'<p>'+esc(x.name)+' · SKU '+esc(x.sku)+' · Stock '+esc(x.stock_qty)+' · Alert at '+esc(x.low_stock_at)+'</p>').join(''):'<p class="muted">No low-stock products.</p>')+'<h3>Recent sales</h3>'+(bizCache.recent?.length?bizCache.recent.map(x=>'<p>'+esc(x.reference)+' · '+esc(x.status)+' · '+esc(x.total)+'</p>').join(''):'<p class="muted">No sales yet.</p>');}
if(bizTab==='customers'){p.innerHTML='<h3>Add customer</h3><form onsubmit="addCustomer(event)" style="display:grid;gap:8px"><input name="name" required placeholder="Customer name"><input name="phone" placeholder="Phone"><input name="email" type="email" placeholder="Email"><textarea name="notes" placeholder="Notes"></textarea><button class="primary">Save customer</button></form><h3>Customer list ('+bizCache.customers.length+')</h3>'+bizCache.customers.map(x=>'<p>'+esc(x.name)+' · '+esc(x.phone)+' · '+esc(x.email)+'</p>').join('');}
if(bizTab==='products'){p.innerHTML='<h3>Add product</h3><form onsubmit="addProduct(event)" style="display:grid;gap:8px"><input name="name" required placeholder="Product name"><input name="sku" required placeholder="SKU / Product code"><input name="unit_price" type="number" min="0" step="0.01" required placeholder="Unit price"><input name="stock_qty" type="number" min="0" step="0.01" value="0" placeholder="Opening stock"><input name="low_stock_at" type="number" min="0" step="0.01" value="5" placeholder="Low stock alert level"><button class="primary">Save product</button></form><h3>Inventory ('+bizCache.products.length+')</h3>'+bizCache.products.map(x=>'<p>'+esc(x.name)+' · SKU '+esc(x.sku)+' · Price '+esc(x.unit_price)+' · Stock '+esc(x.stock_qty)+'</p>').join('');}
if(bizTab==='sales'){p.innerHTML='<h3>Create sale (draft)</h3><form onsubmit="createSale(event)" style="display:grid;gap:8px"><select name="customer_id"><option value="">Walk-in / no customer</option>'+bizCache.customers.map(x=>'<option value="'+x.id+'">'+esc(x.name)+'</option>').join('')+'</select><select name="product_id" required><option value="">Select product</option>'+bizCache.products.map(x=>'<option value="'+x.id+'">'+esc(x.name)+' · stock '+esc(x.stock_qty)+' · '+esc(x.unit_price)+'</option>').join('')+'</select><input name="quantity" type="number" min="0.01" step="0.01" value="1" required><button class="primary">Create draft sale</button></form><h3>Sales history</h3>'+bizCache.sales.map(x=>'<p>'+esc(x.reference)+' · '+esc(x.customer||'Walk-in')+' · '+esc(x.total)+' · '+esc(x.status)+(x.status==='draft'?' <button onclick="confirmSale('+x.id+')">Confirm sale</button>':'')+'</p>').join('');}}
async function addCustomer(e){e.preventDefault();let f=new FormData(e.target);try{await api('customers',{method:'POST',body:JSON.stringify(Object.fromEntries(f))});e.target.reset();await loadDashboard();showBizTab('customers')}catch(x){alert(x.message)}}
async function addProduct(e){e.preventDefault();let f=new FormData(e.target),d=Object.fromEntries(f);['unit_price','stock_qty','low_stock_at'].forEach(k=>d[k]=Number(d[k]));try{await api('products',{method:'POST',body:JSON.stringify(d)});e.target.reset();await loadDashboard();showBizTab('products')}catch(x){alert(x.message)}}
async function createSale(e){e.preventDefault();let f=new FormData(e.target),customer=f.get('customer_id');let body={customer_id:customer?Number(customer):null,items:[{product_id:Number(f.get('product_id')),quantity:Number(f.get('quantity'))}]};try{let d=await api('sales',{method:'POST',body:JSON.stringify(body)});alert('Draft sale created: '+d.reference+' · Total '+d.total+' (stock not deducted yet)');await loadDashboard();showBizTab('sales')}catch(x){alert(x.message)}}
async function confirmSale(id){if(!confirm('Confirm this sale and deduct stock?'))return;try{await api('sales/'+id+'/confirm',{method:'POST'});await loadDashboard();showBizTab('sales')}catch(x){alert(x.message)}}
function newChat(){showChat();cid=null;$('messages').innerHTML='<div class="welcome"><h1>What can we build today?</h1><p>Your private business assistant. Ask in বাংলা, Banglish or English.</p></div>'}
async function status(){try{let d=await(await fetch('/api/health')).json();$('status').textContent=d.ollama==='connected'?'● Local AI connected':'● Ollama not connected';$('status').style.color=d.ollama==='connected'?'#39d5a0':'#ffb86b'}catch{$('status').textContent='Status unavailable'}}
async function history(){try{let xs=await(await fetch('/api/conversations',{headers:apiAdminToken?{'Authorization':'Bearer '+apiAdminToken}:{}})).json();$('history').innerHTML='';xs.forEach(x=>{let b=document.createElement('button');b.className='historyItem';b.textContent=x.title;b.onclick=()=>load(x.id);$('history').append(b)})}catch{}}
async function load(id){let d=await(await fetch('/api/conversations/'+id,{headers:apiAdminToken?{'Authorization':'Bearer '+apiAdminToken}:{}})).json();cid=id;$('messages').innerHTML='';d.messages.forEach(m=>add(m.role,m.content))}
async function send(){let t=$('prompt').value.trim();if(!t)return;$('prompt').value='';add('user',t);let p=add('assistant','Thinking…');try{let r=await fetch('/api/chat',{method:'POST',headers:{'Content-Type':'application/json',...(apiAdminToken?{'Authorization':'Bearer '+apiAdminToken}:{})},body:JSON.stringify({message:t,conversation_id:cid})});let d=await r.json();if(!r.ok)throw Error(d.detail||'Request failed');cid=d.conversation_id;p.textContent=d.answer;history()}catch(e){p.textContent='Error: '+e.message+'\\nCheck Ollama is running and a model is downloaded.'}}
status();history();
</script></body></html>"""
