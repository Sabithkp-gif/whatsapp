from flask import Flask, request, session, jsonify, redirect, url_for, render_template_string, send_file
from flask_session import Session
from werkzeug.security import generate_password_hash, check_password_hash
from io import BytesIO
from datetime import datetime
import uuid
import os

app = Flask(__name__)
app.secret_key = os.environ.get("CHAT_SECRET", "change-this-secret-key")

# Server-side filesystem-backed sessions are optional. If Flask-Session is installed,
# this keeps session data small and suitable for low-RAM phones.
app.config.update(
    SESSION_TYPE="filesystem",
    SESSION_FILE_DIR=os.path.join(os.getcwd(), ".flask_session"),
    SESSION_PERMANENT=False,
    SESSION_USE_SIGNER=True,
)
os.makedirs(app.config["SESSION_FILE_DIR"], exist_ok=True)
Session(app)

# Lightweight in-memory application data.
users = {}
messages = []
audio_store = {}  # audio_id -> {"data": bytes, "mime": str, "owner": str}
MAX_MESSAGES = 500

AVATARS = ["😀", "😎", "🤖", "👽", "🐱", "🐼", "🦊", "🐸", "🔥", "⭐"]

PAGE = r"""
<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<title>GlassChat</title>
<style>
:root{--bg:#08111f;--card:rgba(255,255,255,.09);--line:rgba(255,255,255,.14);
--text:#eef5ff;--muted:#a9b7ca;--accent:#6ea8ff;--accent2:#9b7cff;--danger:#ff667d}
*{box-sizing:border-box}body{margin:0;min-height:100vh;background:
radial-gradient(circle at 15% 10%,#19365d 0,transparent 35%),
radial-gradient(circle at 90% 90%,#321c58 0,transparent 38%),var(--bg);
font-family:system-ui,-apple-system,Segoe UI,sans-serif;color:var(--text)}
.app{width:min(100%,440px);min-height:100vh;margin:auto;padding:14px}
.glass{background:var(--card);border:1px solid var(--line);backdrop-filter:blur(18px);
-webkit-backdrop-filter:blur(18px);box-shadow:0 18px 50px #0004;border-radius:24px}
.login{margin-top:12vh;padding:25px}.logo{font-size:28px;font-weight:800;margin-bottom:5px}
.muted{color:var(--muted);font-size:13px}.field{width:100%;padding:13px 14px;margin:7px 0;border:1px solid var(--line);
border-radius:14px;background:#ffffff0c;color:var(--text);outline:none}.field:focus{border-color:var(--accent)}
button{border:0;border-radius:14px;padding:12px 15px;background:linear-gradient(135deg,var(--accent),var(--accent2));
color:white;font-weight:700;cursor:pointer}button.secondary{background:#ffffff12;border:1px solid var(--line)}
button.danger{background:var(--danger)}button:disabled{opacity:.5}
.header{padding:16px;display:flex;align-items:center;justify-content:space-between;margin-bottom:10px}
.tabs{display:flex;gap:7px;padding:7px;margin-bottom:10px}.tab{flex:1;background:transparent;color:var(--muted)}
.tab.active{background:#ffffff12;color:var(--text)}
.view{display:none}.view.active{display:block}
.messages{height:58vh;min-height:300px;overflow:auto;padding:10px}.msg{display:flex;margin:8px 0;animation:up .22s ease both}
.msg.mine{justify-content:flex-end}.bubble{max-width:80%;padding:10px 12px;border-radius:17px;background:#ffffff10;border:1px solid var(--line)}
.mine .bubble{background:linear-gradient(135deg,#527ed8,#7656b8);border:0}.meta{font-size:10px;color:#b8c5d8;margin-top:4px}
.composer{padding:10px;display:flex;gap:7px;align-items:center}.composer input{flex:1;margin:0}
.rec{width:46px;padding:12px 0}.recording{animation:pulse 1s infinite}
.avatar{font-size:40px}.avatar-grid{display:flex;flex-wrap:wrap;gap:8px;margin:10px 0}
.avatar-choice{font-size:24px;padding:8px;background:#ffffff0b;border:1px solid var(--line)}
.profile{padding:18px}.row{display:flex;align-items:center;gap:14px}.spacer{flex:1}
.audio{width:100%;margin-top:5px}.notice{padding:10px;border-radius:13px;background:#ffffff09;color:var(--muted);font-size:12px}
@keyframes up{from{opacity:0;transform:translateY(8px)}to{opacity:1;transform:none}}
@keyframes pulse{50%{box-shadow:0 0 0 8px #ff667d22}}
</style>
</head>
<body>
<div class="app">
{% if not logged_in %}
<div class="glass login">
<div class="logo">💬 GlassChat</div><div class="muted">Simple low-RAM mobile chat</div>
<form id="loginForm">
<input class="field" id="username" placeholder="Username" maxlength="24" required autocomplete="username">
<input class="field" id="password" placeholder="Password" maxlength="128" type="password" required autocomplete="current-password">
<button style="width:100%;margin-top:8px">Login / Register</button>
</form><p class="muted">First login with a new username creates the account automatically.</p>
</div>
{% else %}
<div class="glass header"><div><b>💬 GlassChat</b><div class="muted">Signed in as {{ username }}</div></div>
<button class="secondary" id="logout">Logout</button></div>
<div class="glass tabs"><button class="tab active" data-view="chat">Chat Room</button><button class="tab" data-view="profile">Account</button></div>

<section id="chat" class="view active">
<div class="glass messages" id="messages"></div>
<div class="glass composer">
<input class="field" id="text" maxlength="1000" placeholder="Type a message…">
<button id="send">Send</button><button class="rec secondary" id="record" title="Voice note">🎙️</button>
</div>
</section>

<section id="profile" class="view">
<div class="glass profile">
<div class="row"><div class="avatar" id="avatarPreview">{{ avatar }}</div><div><b>{{ username }}</b><div class="muted">{{ role }}</div></div></div>
<h4>Choose avatar</h4><div class="avatar-grid" id="avatarGrid">
{% for a in avatars %}<button class="avatar-choice secondary" data-avatar="{{ a }}">{{ a }}</button>{% endfor %}
</div>
{% if role == "host" %}
<hr style="border-color:var(--line);border-width:1px 0 0">
<h4>Host controls</h4><button class="danger" id="clearData">Clear all messages & audio</button>
{% endif %}
</div></section>
{% endif %}
</div>
<script>
const loggedIn={{ 'true' if logged_in else 'false' }};
let lastCount=0, mediaRecorder=null, chunks=[], polling=null;

async function api(url, options={}) {
  const r=await fetch(url,{...options,headers:{'Content-Type':'application/json',...(options.headers||{})}});
  const data=await r.json().catch(()=>({}));
  if(!r.ok) throw new Error(data.error||'Request failed');
  return data;
}

if(!loggedIn){
 document.getElementById('loginForm').addEventListener('submit',async e=>{
  e.preventDefault();
  try{await api('/login',{method:'POST',body:JSON.stringify({
    username:username.value.trim(),password:password.value
  })});location.reload()}catch(err){alert(err.message)}
 });
}else{
 document.querySelectorAll('.tab').forEach(b=>b.onclick=()=>{
  document.querySelectorAll('.tab').forEach(x=>x.classList.remove('active'));
  document.querySelectorAll('.view').forEach(x=>x.classList.remove('active'));
  b.classList.add('active');document.getElementById(b.dataset.view).classList.add('active');
 });
 logout.onclick=async()=>{await fetch('/logout',{method:'POST'});location.reload()};

 async function refresh(){
  try{
   const d=await api('/messages');
   if(d.messages.length!==lastCount || d.messages.length===0){
    messages.innerHTML='';
    d.messages.forEach(m=>{
      const el=document.createElement('div');el.className='msg '+(m.username===d.me?'mine':'');
      const b=document.createElement('div');b.className='bubble';
      const who=document.createElement('div');who.textContent=(m.avatar||'🙂')+' '+m.username;
      b.appendChild(who);
      if(m.text){const t=document.createElement('div');t.textContent=m.text;b.appendChild(t)}
      if(m.audio_id){const au=document.createElement('audio');au.controls=true;au.className='audio';au.src='/audio/'+m.audio_id;b.appendChild(au)}
      const meta=document.createElement('div');meta.className='meta';meta.textContent=m.time;b.appendChild(meta);
      el.appendChild(b);messages.appendChild(el);
    });
    messages.scrollTop=messages.scrollHeight;lastCount=d.messages.length;
   }
  }catch(e){}
 }
 send.onclick=async()=>{const v=text.value.trim();if(!v)return;
  try{await api('/send',{method:'POST',body:JSON.stringify({text:v})});text.value='';await refresh()}catch(e){alert(e.message)}
 };
 text.addEventListener('keydown',e=>{if(e.key==='Enter'&&!e.shiftKey){e.preventDefault();send.click()}});
 document.querySelectorAll('[data-avatar]').forEach(b=>b.onclick=async()=>{
  try{const d=await api('/profile',{method:'POST',body:JSON.stringify({avatar:b.dataset.avatar})});avatarPreview.textContent=d.avatar}catch(e){alert(e.message)}
 });
 const clear=document.getElementById('clearData'); if(clear) clear.onclick=async()=>{
  if(confirm('Delete all messages and audio?')){try{await api('/clear',{method:'POST'});await refresh()}catch(e){alert(e.message)}}
 };

 record.onclick=async()=>{
  if(mediaRecorder && mediaRecorder.state==='recording'){mediaRecorder.stop();return}
  if(!navigator.mediaDevices?.getUserMedia){alert('Microphone recording is not supported by this browser.');return}
  try{
   const stream=await navigator.mediaDevices.getUserMedia({audio:true});
   chunks=[];mediaRecorder=new MediaRecorder(stream,{mimeType:'audio/webm'});
   mediaRecorder.ondataavailable=e=>{if(e.data.size)chunks.push(e.data)};
   mediaRecorder.onstop=async()=>{
    stream.getTracks().forEach(t=>t.stop());record.classList.remove('recording');record.textContent='🎙️';
    const blob=new Blob(chunks,{type:'audio/webm'});const fd=new FormData();fd.append('audio',blob,'voice.webm');
    const r=await fetch('/voice',{method:'POST',body:fd});if(!r.ok)alert('Voice upload failed');await refresh();
   };
   mediaRecorder.start();record.classList.add('recording');record.textContent='⏹️';
  }catch(e){alert('Microphone permission was denied or unavailable.')}
 };
 refresh();polling=setInterval(refresh,2500);
}
</script>
</body></html>
"""

def current_user():
    return session.get("username")

def clean_username(value):
    return isinstance(value, str) and 1 <= len(value.strip()) <= 24 and all(c.isalnum() or c in "_-" for c in value.strip())

@app.get("/")
def index():
    u=current_user()
    user=users.get(u) if u else None
    return render_template_string(PAGE, logged_in=bool(user), username=u or "",
                                  avatar=user["avatar"] if user else "🙂",
                                  role=user["role"] if user else "",
                                  avatars=AVATARS)

@app.post("/login")
def login():
    data=request.get_json(silent=True) or {}
    username=(data.get("username") or "").strip()
    password=data.get("password") or ""
    if not clean_username(username) or not password:
        return jsonify(error="Use a valid username (letters/numbers/_/-) and a password."),400
    if username not in users:
        users[username]={"password":generate_password_hash(password),"avatar":"😀",
                         "role":"host" if not users else "user"}
    elif not check_password_hash(users[username]["password"], password):
        return jsonify(error="Incorrect password."),401
    session["username"]=username
    return jsonify(ok=True,role=users[username]["role"])

@app.post("/logout")
def logout():
    session.clear()
    return jsonify(ok=True)

@app.get("/messages")
def get_messages():
    u=current_user()
    if not u or u not in users:return jsonify(error="Login required"),401
    return jsonify(me=u,messages=[m.copy() for m in messages])

@app.post("/send")
def send_message():
    u=current_user()
    if not u or u not in users:return jsonify(error="Login required"),401
    data=request.get_json(silent=True) or {}
    text=(data.get("text") or "").strip()
    if not text:return jsonify(error="Empty message"),400
    messages.append({"id":str(uuid.uuid4()),"username":u,"avatar":users[u]["avatar"],
                     "text":text[:1000],"audio_id":None,
                     "time":datetime.now().strftime("%H:%M")})
    del messages[:-MAX_MESSAGES]
    return jsonify(ok=True)

@app.post("/voice")
def voice():
    u=current_user()
    if not u or u not in users:return jsonify(error="Login required"),401
    f=request.files.get("audio")
    if not f:return jsonify(error="No audio received"),400
    data=f.read()
    if len(data)>2*1024*1024:return jsonify(error="Voice note too large (2 MB max)."),413
    aid=str(uuid.uuid4())
    audio_store[aid]={"data":data,"mime":"audio/webm","owner":u}
    messages.append({"id":str(uuid.uuid4()),"username":u,"avatar":users[u]["avatar"],
                     "text":"","audio_id":aid,"time":datetime.now().strftime("%H:%M")})
    del messages[:-MAX_MESSAGES]
    return jsonify(ok=True)

@app.get("/audio/<audio_id>")
def audio(audio_id):
    item=audio_store.get(audio_id)
    if not item:return ("Not found",404)
    return send_file(BytesIO(item["data"]),mimetype=item["mime"],download_name="voice.webm")

@app.post("/profile")
def profile():
    u=current_user()
    if not u or u not in users:return jsonify(error="Login required"),401
    data=request.get_json(silent=True) or {}
    avatar=data.get("avatar")
    if avatar not in AVATARS:return jsonify(error="Invalid avatar"),400
    users[u]["avatar"]=avatar
    for m in messages:
        if m["username"]==u:m["avatar"]=avatar
    return jsonify(ok=True,avatar=avatar)

@app.post("/clear")
def clear():
    u=current_user()
    if not u or users.get(u,{}).get("role")!="host":
        return jsonify(error="Host access required"),403
    messages.clear()
    audio_store.clear()
    return jsonify(ok=True)

if __name__=="__main__":
    print("GlassChat running on http://127.0.0.1:5000")
    app.run(host="0.0.0.0",port=int(os.environ.get("PORT",5000)),debug=False,threaded=True)
