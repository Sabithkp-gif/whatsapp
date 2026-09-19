from flask import Flask, request, session, jsonify, render_template_string, send_file
from flask_session import Session
from io import BytesIO
from datetime import datetime
import uuid
import os

app = Flask(__name__)
app.secret_key = os.environ.get("CHAT_SECRET") or os.urandom(32)

app.config.update(
    SESSION_TYPE="filesystem",
    SESSION_FILE_DIR=os.path.join("/tmp", "glasschat_sessions"),
    SESSION_PERMANENT=False,
    SESSION_USE_SIGNER=True,
)
os.makedirs(app.config["SESSION_FILE_DIR"], exist_ok=True)
Session(app)

users = {}
messages = []
audio_store = {}
MAX_MESSAGES = 500
MAX_AUDIO_BYTES = 2 * 1024 * 1024
AVATARS = ["😀", "😎", "🤖", "👽", "🐱", "🐼", "🦊", "🐸", "🔥", "⭐"]

PAGE = r"""
<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<title>GlassChat</title>
<style>
:root{--bg:#08111f;--card:rgba(255,255,255,.09);--line:rgba(255,255,255,.14);--text:#eef5ff;--muted:#a9b7ca;--accent:#6ea8ff;--accent2:#9b7cff;--danger:#ff667d}
*{box-sizing:border-box}body{margin:0;min-height:100vh;background:radial-gradient(circle at 15% 10%,#19365d 0,transparent 35%),radial-gradient(circle at 90% 90%,#321c58 0,transparent 38%),var(--bg);font-family:system-ui,-apple-system,Segoe UI,sans-serif;color:var(--text)}
.app{width:min(100%,440px);min-height:100vh;margin:auto;padding:14px}.glass{background:var(--card);border:1px solid var(--line);backdrop-filter:blur(18px);-webkit-backdrop-filter:blur(18px);box-shadow:0 18px 50px #0004;border-radius:24px}.logo{font-size:28px;font-weight:800;margin-bottom:5px}.muted{color:var(--muted);font-size:13px}.field{width:100%;padding:13px 14px;margin:7px 0;border:1px solid var(--line);border-radius:14px;background:#ffffff0c;color:var(--text);outline:none}.field:focus{border-color:var(--accent)}
button{border:0;border-radius:14px;padding:12px 15px;background:linear-gradient(135deg,var(--accent),var(--accent2));color:white;font-weight:700;cursor:pointer}button.secondary{background:#ffffff12;border:1px solid var(--line)}button.danger{background:var(--danger)}button:disabled{opacity:.5}.header{padding:16px;display:flex;align-items:center;justify-content:space-between;margin-bottom:10px}.tabs{display:flex;gap:7px;padding:7px;margin-bottom:10px}.tab{flex:1;background:transparent;color:var(--muted)}.tab.active{background:#ffffff12;color:var(--text)}.view{display:none}.view.active{display:block}.messages{height:58vh;min-height:300px;overflow:auto;padding:10px}.msg{display:flex;margin:8px 0;animation:up .22s ease both}.msg.mine{justify-content:flex-end}.bubble{max-width:80%;padding:10px 12px;border-radius:17px;background:#ffffff10;border:1px solid var(--line)}.mine .bubble{background:linear-gradient(135deg,#527ed8,#7656b8);border:0}.meta{font-size:10px;color:#b8c5d8;margin-top:4px}.composer{padding:10px;display:flex;gap:7px;align-items:center}.composer input{flex:1;margin:0}.rec{width:46px;padding:12px 0}.recording{animation:pulse 1s infinite}.avatar{font-size:40px}.avatar-grid{display:flex;flex-wrap:wrap;gap:8px;margin:10px 0}.avatar-choice{font-size:24px;padding:8px;background:#ffffff0b;border:1px solid var(--line)}.profile{padding:18px}.row{display:flex;align-items:center;gap:14px}.audio{width:100%;margin-top:5px}@keyframes up{from{opacity:0;transform:translateY(8px)}to{opacity:1;transform:none}}@keyframes pulse{50%{box-shadow:0 0 0 8px #ff667d22}}
</style>
</head>
<body>
<div class="app">
<div class="glass header"><div><b>💬 GlassChat</b><div class="muted">Chatting as {{ username }}</div></div><button class="secondary" id="logout">Logout</button></div>
<div class="glass tabs"><button class="tab active" data-view="chat">Chat Room</button><button class="tab" data-view="profile">Profile</button></div>
<section id="chat" class="view active"><div class="glass messages" id="messages"></div><div class="glass composer"><input class="field" id="text" maxlength="1000" placeholder="Type a message…"><button id="send">Send</button><button class="rec secondary" id="record" title="Voice note">🎙️</button></div></section>
<section id="profile" class="view"><div class="glass profile"><div class="row"><div class="avatar" id="avatarPreview">{{ avatar }}</div><div><b id="profileName">{{ username }}</b><div class="muted">{{ role }}</div></div></div><h4>Display name</h4><div class="row"><input class="field" id="displayName" maxlength="24" value="{{ username }}" placeholder="Your name"><button id="saveName">Save</button></div><h4>Choose avatar</h4><div class="avatar-grid">{% for a in avatars %}<button class="avatar-choice secondary" data-avatar="{{ a }}">{{ a }}</button>{% endfor %}</div>{% if role == "host" %}<hr style="border-color:var(--line);border-width:1px 0 0"><h4>Host controls</h4><button class="danger" id="clearData">Clear all messages & audio</button>{% endif %}</div></section>
</div>
<script>
let lastCount=0,mediaRecorder=null,chunks=[];
const $=id=>document.getElementById(id);
async function api(url,options={}){const r=await fetch(url,{...options,headers:{...(options.body instanceof FormData?{}:{'Content-Type':'application/json'}),...(options.headers||{})}});const d=await r.json().catch(()=>({}));if(!r.ok)throw new Error(d.error||'Request failed');return d}
$('logout').onclick=async()=>{await fetch('/logout',{method:'POST'});location.reload()};
document.querySelectorAll('.tab').forEach(b=>b.onclick=()=>{document.querySelectorAll('.tab').forEach(x=>x.classList.remove('active'));document.querySelectorAll('.view').forEach(x=>x.classList.remove('active'));b.classList.add('active');$(b.dataset.view).classList.add('active')});
async function refresh(){try{const d=await api('/messages');if(d.messages.length!==lastCount||d.messages.length===0){$('messages').innerHTML='';d.messages.forEach(m=>{const e=document.createElement('div');e.className='msg '+(m.username===d.me?'mine':'');const b=document.createElement('div');b.className='bubble';const w=document.createElement('div');w.textContent=(m.avatar||'🙂')+' '+m.username;b.appendChild(w);if(m.text){const t=document.createElement('div');t.textContent=m.text;b.appendChild(t)}if(m.audio_id){const a=document.createElement('audio');a.controls=true;a.className='audio';a.src='/audio/'+encodeURIComponent(m.audio_id);b.appendChild(a)}const meta=document.createElement('div');meta.className='meta';meta.textContent=m.time;b.appendChild(meta);e.appendChild(b);$('messages').appendChild(e)});$('messages').scrollTop=$('messages').scrollHeight;lastCount=d.messages.length}}catch(e){}}
$('send').onclick=async()=>{const v=$('text').value.trim();if(!v)return;try{await api('/send',{method:'POST',body:JSON.stringify({text:v})});$('text').value='';await refresh()}catch(e){alert(e.message)}};$('text').addEventListener('keydown',e=>{if(e.key==='Enter'&&!e.shiftKey){e.preventDefault();$('send').click()}});
document.querySelectorAll('[data-avatar]').forEach(b=>b.onclick=async()=>{try{const d=await api('/profile',{method:'POST',body:JSON.stringify({avatar:b.dataset.avatar})});$('avatarPreview').textContent=d.avatar}catch(e){alert(e.message)}});
$('saveName').onclick=async()=>{try{const d=await api('/profile',{method:'POST',body:JSON.stringify({username:$('displayName').value.trim()})});$('profileName').textContent=d.username;location.reload()}catch(e){alert(e.message)}};
const clear=$('clearData');if(clear)clear.onclick=async()=>{if(confirm('Delete all messages and audio?')){try{await api('/clear',{method:'POST'});lastCount=-1;await refresh()}catch(e){alert(e.message)}}};
$('record').onclick=async()=>{if(mediaRecorder&&mediaRecorder.state==='recording'){mediaRecorder.stop();return}if(!navigator.mediaDevices?.getUserMedia){alert('Microphone recording is not supported by this browser.');return}try{const stream=await navigator.mediaDevices.getUserMedia({audio:true});chunks=[];const options=MediaRecorder.isTypeSupported('audio/webm')?{mimeType:'audio/webm'}:{};mediaRecorder=new MediaRecorder(stream,options);mediaRecorder.ondataavailable=e=>{if(e.data.size)chunks.push(e.data)};mediaRecorder.onstop=async()=>{stream.getTracks().forEach(t=>t.stop());$('record').classList.remove('recording');$('record').textContent='🎙️';const fd=new FormData();fd.append('audio',new Blob(chunks,{type:mediaRecorder.mimeType||'audio/webm'}),'voice.webm');try{await api('/voice',{method:'POST',body:fd});await refresh()}catch(e){alert(e.message)}};mediaRecorder.start();$('record').classList.add('recording');$('record').textContent='⏹️'}catch(e){alert('Microphone permission was denied or unavailable.')}};
refresh();setInterval(refresh,2500);
</script>
</body></html>
"""


def get_or_create_user():
    sid = session.get("client_id")
    if not sid:
        sid = uuid.uuid4().hex
        session["client_id"] = sid
    if sid not in users:
        users[sid] = {"username": f"Guest-{len(users) + 1}", "avatar": "😀", "role": "host" if not users else "user"}
    return users[sid]


def valid_display_name(value):
    return isinstance(value, str) and 1 <= len(value.strip()) <= 24


def append_message(message):
    messages.append(message)
    del messages[:-MAX_MESSAGES]


@app.get("/")
def index():
    user = get_or_create_user()
    return render_template_string(PAGE, username=user["username"], avatar=user["avatar"], role=user["role"], avatars=AVATARS)


@app.post("/logout")
def logout():
    session.clear()
    return jsonify(ok=True)


@app.get("/messages")
def get_messages():
    user = get_or_create_user()
    return jsonify(me=user["username"], messages=[m.copy() for m in messages])


@app.post("/send")
def send_message():
    user = get_or_create_user()
    data = request.get_json(silent=True) or {}
    text = (data.get("text") or "").strip()
    if not text:
        return jsonify(error="Empty message"), 400
    append_message({"id": str(uuid.uuid4()), "username": user["username"], "avatar": user["avatar"], "text": text[:1000], "audio_id": None, "time": datetime.now().strftime("%H:%M")})
    return jsonify(ok=True)


@app.post("/voice")
def voice():
    user = get_or_create_user()
    file = request.files.get("audio")
    if not file:
        return jsonify(error="No audio received"), 400
    data = file.read(MAX_AUDIO_BYTES + 1)
    if len(data) > MAX_AUDIO_BYTES:
        return jsonify(error="Voice note too large (2 MB max)."), 413
    audio_id = str(uuid.uuid4())
    audio_store[audio_id] = {"data": data, "mime": file.mimetype or "audio/webm", "owner": user["username"]}
    append_message({"id": str(uuid.uuid4()), "username": user["username"], "avatar": user["avatar"], "text": "", "audio_id": audio_id, "time": datetime.now().strftime("%H:%M")})
    return jsonify(ok=True)


@app.get("/audio/<audio_id>")
def audio(audio_id):
    item = audio_store.get(audio_id)
    if not item:
        return "Not found", 404
    return send_file(BytesIO(item["data"]), mimetype=item["mime"], download_name="voice.webm")


@app.post("/profile")
def profile():
    user = get_or_create_user()
    data = request.get_json(silent=True) or {}
    if "avatar" in data:
        if data["avatar"] not in AVATARS:
            return jsonify(error="Invalid avatar"), 400
        user["avatar"] = data["avatar"]
        for message in messages:
            if message["username"] == user["username"]:
                message["avatar"] = user["avatar"]
    if "username" in data:
        name = (data.get("username") or "").strip()
        if not valid_display_name(name):
            return jsonify(error="Name must be 1-24 characters."), 400
        old_name = user["username"]
        user["username"] = name
        for message in messages:
            if message["username"] == old_name:
                message["username"] = name
        for item in audio_store.values():
            if item["owner"] == old_name:
                item["owner"] = name
    return jsonify(ok=True, avatar=user["avatar"], username=user["username"])


@app.post("/clear")
def clear():
    user = get_or_create_user()
    if user.get("role") != "host":
        return jsonify(error="Host access required"), 403
    messages.clear()
    audio_store.clear()
    return jsonify(ok=True)


if __name__ == "__main__":
    print("GlassChat starting on the configured PORT")
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)), debug=False, threaded=True)
