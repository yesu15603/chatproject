from flask import Flask, render_template, request, redirect, session
from flask_socketio import SocketIO, emit, join_room
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
from werkzeug.utils import secure_filename
import os

app = Flask(__name__)
app.config['SECRET_KEY'] = 'secret'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///chat.db'
app.config['UPLOAD_FOLDER'] = 'static/uploads'

os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

db = SQLAlchemy(app)
socketio = SocketIO(app, async_mode='eventlet')

# ---------------- DATABASE ---------------- #

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(100), unique=True)
    photo = db.Column(db.String(200), default="default.png")

class Message(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    sender = db.Column(db.String(100))
    receiver = db.Column(db.String(100))
    text = db.Column(db.String(500))
    time = db.Column(db.String(100))
    seen = db.Column(db.Boolean, default=False)

with app.app_context():
    db.create_all()

online_users = set()

# ---------------- ROUTES ---------------- #

@app.route('/', methods=['GET','POST'])
def login():
    if request.method == 'POST':
        email = request.form['email']
        session['email'] = email
        
        if not User.query.filter_by(email=email).first():
            db.session.add(User(email=email))
            db.session.commit()
        
        return redirect('/chat')
    return render_template('login.html')

@app.route('/chat')
def chat():
    if 'email' not in session:
        return redirect('/')
    
    users = User.query.filter(User.email != session['email']).all()
    return render_template('chat.html', users=users, me=session['email'])

@app.route('/upload', methods=['POST'])
def upload():
    file = request.files['photo']
    if file:
        filename = secure_filename(file.filename)
        path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(path)

        user = User.query.filter_by(email=session['email']).first()
        user.photo = filename
        db.session.commit()

    return redirect('/chat')

# ---------------- SOCKET ---------------- #

@socketio.on('connect')
def connect():
    if 'email' in session:
        online_users.add(session['email'])
        emit('update_users', list(online_users), broadcast=True)

@socketio.on('disconnect')
def disconnect():
    if 'email' in session:
        online_users.discard(session['email'])
        emit('update_users', list(online_users), broadcast=True)

@socketio.on('join')
def join(data):
    join_room(data['room'])

@socketio.on('send_message')
def handle_message(data):
    sender = data['sender']
    receiver = data['receiver']
    text = data['message']
    time = datetime.now().strftime("%H:%M")

    msg = Message(sender=sender, receiver=receiver, text=text, time=time, seen=False)
    db.session.add(msg)
    db.session.commit()

    room = "_".join(sorted([sender, receiver]))

    emit('receive_message', {
        'id': msg.id,
        'sender': sender,
        'message': text,
        'time': time,
        'seen': False
    }, room=room)

@socketio.on('mark_seen')
def mark_seen(data):
    msg = Message.query.get(data['id'])
    if msg:
        msg.seen = True
        db.session.commit()
        emit('message_seen', {'id': msg.id}, broadcast=True)

@socketio.on('typing')
def typing(data):
    emit('show_typing', data, room=data['room'], include_self=False)

@socketio.on('delete_message')
def delete_message(data):
    msg = Message.query.get(data['id'])
    if msg:
        db.session.delete(msg)
        db.session.commit()
        emit('message_deleted', {'id': data['id']}, broadcast=True)

if __name__ == '__main__':
    socketio.run(app, debug=True)