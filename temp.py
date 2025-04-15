import sqlite3
import hashlib
from flask import Flask, render_template, redirect, url_for, flash, request, session
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from flask_socketio import join_room, leave_room, send, SocketIO
import random
from string import ascii_uppercase

app = Flask(__name__)
app.config['SECRET_KEY'] = 'dhaoiusdhasoi'

socketio = SocketIO(app)

login_manager = LoginManager(app)
login_manager.login_view = 'login'

rooms = {}


def generate_unique_code(n):
    while True:
        code = ""
        for i in range(n):
            code += random.choice(ascii_uppercase)
        if code not in rooms:
            break
    return code


class User(UserMixin):
    def __init__(self, id, username):
        self.id = id
        self.username = username

    @staticmethod
    def get(user_id):
        conn = sqlite3.connect('users.db')
        c = conn.cursor()
        c.execute('SELECT id, username FROM userdata WHERE id = ?', (user_id,))
        user_row = c.fetchone()
        conn.close()
        if user_row:
            return User(user_row[0], user_row[1])
        return None

    @staticmethod
    def get_by_username(username):
        conn = sqlite3.connect('users.db')
        c = conn.cursor()
        c.execute('SELECT id, username, password FROM userdata WHERE username = ?', (username,))
        user_row = c.fetchone()
        conn.close()
        if user_row:
            return User(user_row[0], user_row[1]), user_row[2]
        return None, None


@login_manager.user_loader
def load_user(user_id):
    return User.get(user_id)


@app.route('/')
def main():
    return render_template('main.html')


@app.route('/home', methods=['GET', 'POST'])
@login_required
def home():
    if request.method == 'POST':
        print(request.form)  # Debug print
        room_code = request.form.get('room_code')
        if 'create_room' in request.form:
            room_code = generate_unique_code(4)
            rooms[room_code] = {"members": 0, "messages": []}
            print("Generated Room Code: ", room_code)  # Debug print

        elif 'enter_room' in request.form:

            if not room_code:
                return render_template("home.html", error="Please enter a room code.", room_code=room_code)

            elif room_code not in rooms:
                return render_template("home.html", error="Room does not exist.", room_code=room_code)

            print("Entered Room Code: ", room_code)  # Debug print

        session["room_code"] = room_code
        session["name"] = current_user.username

        return redirect(url_for('room', room_code=room_code))
    return render_template('home.html')


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password').encode()
        hex_passwd = hashlib.sha3_256(password).hexdigest()

        user, stored_password = User.get_by_username(username)
        if user and hex_passwd == stored_password:
            login_user(user)
            flash('Logged in successfully.', 'success')

            return redirect(url_for('home'))
        else:
            flash('Invalid username or password', 'danger')
    return render_template('login.html')


@app.route('/register', methods=['GET', 'POST'])
def register():
    db_conn = sqlite3.connect("users.db")
    db_cur = db_conn.cursor()
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password').encode()
        hex_passwd = hashlib.sha3_256(password).hexdigest()

        db_cur.execute("SELECT * FROM userdata WHERE username = ? AND password = ?", (username, hex_passwd))
        if db_cur.fetchall():
            flash('Username already exists', 'danger')

            db_cur.close()
        else:
            db_cur.execute("INSERT INTO userdata (username, password) VALUES (?, ?)", (username, hex_passwd))
            flash('Registered successfully', 'success')
            db_conn.commit()
            db_cur.close()
            return redirect(url_for('login'))

    return render_template('register.html')


@app.route("/room")
def room():
    room_code = session.get("room_code")
    print(rooms)
    if room_code is None or session.get("room_code") is None or room_code not in rooms:
        return redirect(url_for("home"))

    return render_template("room.html", room_code=room_code, messages=rooms[room_code]["messages"])


@socketio.on("message")
def message(data):
    room = session.get("room_code")
    if room not in rooms:
        return

    content = {
        "name": session.get("name"), "message": data["data"]
    }
    send(content, to=room)
    rooms[room]["messages"].append(content)
    print(f"{session.get('name')} said: {data['data']}")


@socketio.on("connect")
def connect(auth):
    room = session.get("room_code")
    name = session.get("name")
    if not room or not name:
        return
    if room not in rooms:
        leave_room(room)
        return
    join_room(room)
    send({"name": name, "message": "has entered the room"}, to=room)
    rooms[room]["members"] += 1
    print(f"{name} joined room {room}")


@socketio.on("disconnect")
def disconnect():
    room = session.get("room_code")
    name = session.get("name")
    leave_room(room)

    if room in rooms:
        rooms[room]["members"] -= 1
        if rooms[room]["members"] <= 0:
            del rooms[room]

    send({"name": name, "message": "has left the room"}, to=room)
    print(f"{name} left room {room}")


@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('Logged out successfully', 'success')
    return redirect(url_for('main'))


if __name__ == '__main__':
    socketio.run(app, debug=True)
