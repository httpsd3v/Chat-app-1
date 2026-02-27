from flask import Flask, render_template_string, request, session, redirect, url_for, jsonify
from flask_socketio import SocketIO, join_room, leave_room, send
from datetime import datetime
import sqlite3

# ---------------- CONFIG ----------------
app = Flask(__name__)
app.config['SECRET_KEY'] = 'supersecretkey'
socketio = SocketIO(app, async_mode='threading')  # Windows-safe
DB = 'chat.db'

# ---------------- DATABASE ----------------
def init_db():
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS rooms (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL
        )
    ''')
    c.execute('''
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            room TEXT NOT NULL,
            sender TEXT NOT NULL,
            receiver TEXT,
            message TEXT NOT NULL,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    c.execute("INSERT OR IGNORE INTO rooms (name) VALUES (?)", ("Main",))
    conn.commit()
    conn.close()

init_db()

# ---------------- HTML ----------------
HTML = """
<!DOCTYPE html>
<html>
<head>
<title>Flask Chat</title>
<link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.2/dist/css/bootstrap.min.css" rel="stylesheet">
<script src="https://cdn.socket.io/4.5.4/socket.io.min.js"></script>
<style>
body { background:#0b0b0b; color:white; }
#sidebar { height:80vh; overflow-y:auto; background:#111; padding:10px; border-radius:10px; }
.tab-content { margin-top:10px; }
.tab-pane { height:60vh; overflow-y:auto; padding:10px; border-radius:10px; background:#1a1a1a; }
.message { margin-bottom:5px; padding:5px 10px; border-radius:10px; max-width:75%; word-wrap:break-word; }
.message.self { background:#ffdd95; color:black; margin-left:auto; text-align:right; }
.message.other { background:#222; color:white; margin-right:auto; text-align:left; }
.timestamp { font-size:0.7rem; color:#888; display:block; }
.room-btn.active { background:#ffdd95;color:black; font-weight:bold; }
.user-btn { margin-bottom:5px;width:100%; }
</style>
</head>
<body>
<audio id="notif-sound" src="https://www.soundjay.com/button/beep-07.wav" preload="auto"></audio>
<div class="container mt-3">
{% if not session.get('username') %}
<div class="row justify-content-center">
<div class="col-md-4 text-center">
<h2>Enter Username</h2>
<form method="POST" action="/set_username">
<input name="username" placeholder="Your username" class="form-control mb-2" required>
<button type="submit" class="btn btn-warning w-100 mb-2">Enter Chat</button>
</form>
</div>
</div>
{% else %}
<div class="d-flex justify-content-between mb-2">
<div>Logged in as <b>{{ session.get('username') }}</b></div>
<a href="/logout" class="btn btn-warning btn-sm">Logout</a>
</div>

<div class="row">
<div class="col-md-3">
<div id="sidebar">
<h5>Rooms <button class="btn btn-sm btn-warning" onclick="createRoom()">+</button></h5>
<div id="rooms"></div>
<hr>
<h5>Online Users</h5>
<div id="users"></div>
</div>
</div>

<div class="col-md-9">
<ul class="nav nav-tabs" id="chatTabs" role="tablist">
  <li class="nav-item" role="presentation">
    <button class="nav-link active" id="Main-tab" data-bs-toggle="tab" data-bs-target="#Main" type="button">
        Main <span class="badge bg-warning text-dark ms-1" id="badge-Main" style="display:none">0</span>
    </button>
  </li>
</ul>
<div class="tab-content" id="chatContent">
  <div class="tab-pane fade show active" id="Main" role="tabpanel"></div>
</div>

<div class="input-group mb-3 mt-2">
<input id="msg" type="text" class="form-control" placeholder="Type message, emojis 😀" onkeypress="if(event.key==='Enter') sendMsg()">
<button class="btn btn-warning" onclick="sendMsg()">Send</button>
</div>
</div>
</div>

<script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.2/dist/js/bootstrap.bundle.min.js"></script>
<script>
var socket = io();
var username="{{ session.get('username') }}";
var currentRoom="Main";
var privateUser=null;
var openTabs = {"Main":"Main"};

function loadRooms(){
    fetch("/rooms").then(r=>r.json()).then(data=>{
        let roomsDiv=document.getElementById('rooms');
        roomsDiv.innerHTML="";
        data.forEach(r=>{
            let b=document.createElement('button');
            b.className='btn btn-sm w-100 mb-1 room-btn'+(r.name===currentRoom?' active':'');
            b.innerText=r.name;
            b.onclick=()=>switchRoom(r.name);
            roomsDiv.appendChild(b);
        });
    });
}

function switchRoom(room){
    privateUser=null;
    if(!openTabs[room]){
        addTab(room);
        openTabs[room]=room;
    }
    currentRoom=room;
    var tab = new bootstrap.Tab(document.getElementById(room+'-tab'));
    tab.show();
    loadMessages(room);
    loadRooms();
}

function addTab(name){
    var tabs=document.getElementById('chatTabs');
    var tab=document.createElement('li');
    tab.className='nav-item';
    tab.role='presentation';
    tab.innerHTML=`
        <button class="nav-link" id="${name}-tab" data-bs-toggle="tab" data-bs-target="#${name}" type="button">
            ${name} <span class="badge bg-warning text-dark ms-1" id="badge-${name}" style="display:none">0</span>
        </button>`;
    tabs.appendChild(tab);

    var content=document.getElementById('chatContent');
    var pane=document.createElement('div');
    pane.className='tab-pane fade';
    pane.id=name;
    pane.role='tabpanel';
    content.appendChild(pane);

    tab.querySelector('button').addEventListener('shown.bs.tab', ()=>{
        document.getElementById('badge-'+name).style.display='none';
        document.getElementById('badge-'+name).innerText='0';
    });
}

function loadMessages(room){
    fetch("/history/"+room).then(r=>r.json()).then(data=>{
        var messagesDiv=document.getElementById(room);
        messagesDiv.innerHTML="";
        data.forEach(m=>{
            var div=document.createElement('div');
            div.className='message '+(m.sender===username?'self':'other');
            div.innerHTML=m.sender+(m.receiver?' → '+m.receiver:'')+": "+m.message+
                            `<span class='timestamp'>${m.timestamp}</span>`;
            messagesDiv.appendChild(div);
        });
        messagesDiv.scrollTop=messagesDiv.scrollHeight;
    });
}

function loadUsers(users){
    let usersDiv=document.getElementById('users');
    usersDiv.innerHTML="";
    users.forEach(u=>{
        if(u!==username){
            let b=document.createElement('button');
            b.className='btn btn-sm btn-outline-light w-100 user-btn';
            b.innerText=u;
            b.onclick=()=>{privateChat(u);}
            usersDiv.appendChild(b);
        }
    });
}

function createRoom(){
    let name=prompt("Enter room name:");
    if(!name) return;
    fetch("/create_room",{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({name:name})})
    .then(r=>r.json()).then(data=>{
        if(data.success) switchRoom(name);
        else alert("Room exists!");
    });
}

function privateChat(user){
    privateUser=user;
    if(!openTabs[user]){
        addTab(user);
        openTabs[user]=user;
    }
    currentRoom=user;
    var tab = new bootstrap.Tab(document.getElementById(user+'-tab'));
    tab.show();
    loadMessages(user);
}

socket.on('online_users', loadUsers);

socket.on('message', function(data){
    var room = data.receiver ? data.receiver===username ? data.sender : data.receiver : data.room;
    if(!openTabs[room]){
        addTab(room);
        openTabs[room]=room;
    }
    var div=document.createElement('div');
    div.className='message '+(data.sender===username?'self':'other');
    div.innerHTML=data.sender+(data.receiver?' → '+data.receiver:'')+": "+data.msg+
                    `<span class='timestamp'>${data.timestamp}</span>`;
    document.getElementById(room).appendChild(div);
    var pane = document.getElementById(room);
    pane.scrollTop = pane.scrollHeight;

    if(room !== currentRoom){
        var badge = document.getElementById('badge-'+room);
        var count = parseInt(badge.innerText) || 0;
        badge.innerText = count+1;
        badge.style.display='inline-block';
        document.getElementById('notif-sound').play();
    }
});

function sendMsg(){
    let m=document.getElementById('msg').value.trim();
    if(!m) return;
    socket.emit('message',{username:username, room:currentRoom, msg:m, private:privateUser});
    document.getElementById('msg').value="";
}

window.onload=function(){ loadRooms(); switchRoom("Main"); }
</script>
{% endif %}
</div>
</body>
</html>
"""

# ---------------- ROUTES ----------------
@app.route('/')
def index(): return render_template_string(HTML)

@app.route('/set_username', methods=['POST'])
def set_username():
    username=request.form['username'].strip()
    if username:
        session['username']=username
    return redirect(url_for('index'))

@app.route('/logout')
def logout():
    session.pop('username', None)
    return redirect(url_for('index'))

@app.route('/rooms')
def get_rooms():
    conn=sqlite3.connect(DB)
    c=conn.cursor()
    c.execute("SELECT name FROM rooms")
    rooms=[{"name":r[0]} for r in c.fetchall()]
    conn.close()
    return jsonify(rooms)

@app.route('/create_room', methods=['POST'])
def create_room():
    data=request.get_json()
    name=data.get('name')
    if not name: return jsonify({'success':False})
    conn=sqlite3.connect(DB)
    c=conn.cursor()
    try:
        c.execute("INSERT INTO rooms (name) VALUES (?)",(name,))
        conn.commit()
        conn.close()
        return jsonify({'success':True})
    except sqlite3.IntegrityError:
        return jsonify({'success':False})

@app.route('/history/<room>')
def history(room):
    conn=sqlite3.connect(DB)
    c=conn.cursor()
    c.execute("SELECT sender,receiver,message,timestamp FROM messages WHERE room=? OR receiver=? ORDER BY id ASC",(room,room))
    messages=[{"sender":s,"receiver":r,"message":m,"timestamp":ts} for s,r,m,ts in c.fetchall()]
    conn.close()
    return jsonify(messages)

# ---------------- SOCKETIO ----------------
online_users={}

@socketio.on('join_room')
def handle_join(data):
    sid=request.sid
    username=data['username']
    room=data['room']
    online_users[sid]=username
    join_room(room)
    update_online_users()
    send({'sender':'System','msg':f'{username} joined {room}','timestamp':datetime.now().strftime("%H:%M")}, room=room)

@socketio.on('leave_room')
def handle_leave(data):
    room=data['room']
    leave_room(room)
    send({'sender':'System','msg':f"{data['username']} left {room}",'timestamp':datetime.now().strftime("%H:%M")}, room=room)

@socketio.on('message')
def handle_message(data):
    room=data['room']
    sender=data['username']
    msg=data['msg']
    receiver=data.get('private')
    timestamp=datetime.now().strftime("%H:%M")
    conn=sqlite3.connect(DB)
    c=conn.cursor()
    c.execute("INSERT INTO messages (room,sender,receiver,message) VALUES (?,?,?,?)",(room,sender,receiver,msg))
    conn.commit()
    conn.close()
    target_room=receiver if receiver else room
    send({'sender':sender,'receiver':receiver,'msg':msg,'timestamp':timestamp}, room=target_room)

@socketio.on('disconnect')
def handle_disconnect():
    sid=request.sid
    username=online_users.get(sid)
    if username:
        for room in socketio.rooms(sid):
            leave_room(room)
            send({'sender':'System','msg':f'{username} disconnected','timestamp':datetime.now().strftime("%H:%M")}, room=room)
        del online_users[sid]
    update_online_users()

def update_online_users():
    users=list(online_users.values())
    socketio.emit('online_users',users)

# ---------------- RUN ----------------
if __name__=="__main__":
    socketio.run(app, host="0.0.0.0", port=5000, debug=False)