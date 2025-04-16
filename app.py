import os
import pty
import select
import threading
import tempfile
import subprocess
import shutil
from flask import Flask, render_template, request
from flask_socketio import SocketIO

app = Flask(__name__)
app.config['SECRET_KEY'] = 'secret!'
socketio = SocketIO(app)

# Dictionary to store per-session process info (file descriptor and cleanup function).
terminals = {}

def command_exists(command):
    """Check if a command exists in the system PATH."""
    return shutil.which(command) is not None

@app.route('/')
def index():
    return render_template('index.html')

@socketio.on('run_code')
def handle_run_code(data):
    """
    Receives code and language info from the client.
    Writes the code to a temporary file, compiles (if necessary),
    and then forks a new pseudo-terminal to execute the code.
    The output is then streamed back to the client via Socket.IO.
    """
    sid = request.sid

    # Clean up any previous process for this session.
    if sid in terminals:
        try:
            os.close(terminals[sid]['fd'])
        except Exception:
            pass
        try:
            terminals[sid]['cleanup']()
        except Exception:
            pass
        terminals.pop(sid, None)

    language = data.get('language', 'python')
    code = data.get('code', '')

    # Prepare command and cleanup function based on language.
    if language == 'python':
        tmp = tempfile.NamedTemporaryFile(mode='w+', suffix='.py', delete=False)
        tmp.write(code)
        tmp.flush()
        tmp.close()
        cleanup = lambda: os.remove(tmp.name) if os.path.exists(tmp.name) else None
        command = ["python3", "-u", tmp.name]

    elif language == 'java':
        temp_dir = tempfile.mkdtemp()
        file_path = os.path.join(temp_dir, "Main.java")
        with open(file_path, "w") as f:
            f.write(code)
        compile_proc = subprocess.run(
            ["javac", "Main.java"],
            cwd=temp_dir,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        if compile_proc.returncode != 0:
            error_message = compile_proc.stderr or compile_proc.stdout
            socketio.emit("output", error_message, to=sid)
            shutil.rmtree(temp_dir)
            return
        cleanup = lambda: shutil.rmtree(temp_dir) if os.path.exists(temp_dir) else None
        command = ["java", "-cp", temp_dir, "Main"]

    elif language == 'c':
        temp_dir = tempfile.mkdtemp()
        file_path = os.path.join(temp_dir, "main.c")
        with open(file_path, "w") as f:
            f.write(code)
        compile_proc = subprocess.run(
            ["gcc", "main.c", "-o", "main_exe"],
            cwd=temp_dir,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        if compile_proc.returncode != 0:
            error_message = compile_proc.stderr or compile_proc.stdout
            socketio.emit("output", error_message, to=sid)
            shutil.rmtree(temp_dir)
            return
        cleanup = lambda: shutil.rmtree(temp_dir) if os.path.exists(temp_dir) else None
        command = [os.path.join(temp_dir, "main_exe")]

    elif language == 'c++':
        temp_dir = tempfile.mkdtemp()
        file_path = os.path.join(temp_dir, "main.cpp")
        with open(file_path, "w") as f:
            f.write(code)
        compile_proc = subprocess.run(
            ["g++", "main.cpp", "-o", "main_exe"],
            cwd=temp_dir,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        if compile_proc.returncode != 0:
            error_message = compile_proc.stderr or compile_proc.stdout
            socketio.emit("output", error_message, to=sid)
            shutil.rmtree(temp_dir)
            return
        cleanup = lambda: shutil.rmtree(temp_dir) if os.path.exists(temp_dir) else None
        command = [os.path.join(temp_dir, "main_exe")]

    elif language == 'javascript':
        tmp = tempfile.NamedTemporaryFile(mode='w+', suffix='.js', delete=False)
        tmp.write(code)
        tmp.flush()
        tmp.close()
        cleanup = lambda: os.remove(tmp.name) if os.path.exists(tmp.name) else None
        command = ["node", tmp.name]

    elif language == 'php':
        tmp = tempfile.NamedTemporaryFile(mode='w+', suffix='.php', delete=False)
        tmp.write(code)
        tmp.flush()
        tmp.close()
        cleanup = lambda: os.remove(tmp.name) if os.path.exists(tmp.name) else None
        command = ["php", "-f", tmp.name]

    elif language == 'perl':
        tmp = tempfile.NamedTemporaryFile(mode='w+', suffix='.pl', delete=False)
        tmp.write(code)
        tmp.flush()
        tmp.close()
        cleanup = lambda: os.remove(tmp.name) if os.path.exists(tmp.name) else None
        command = ["perl", tmp.name]

    else:
        socketio.emit("output", "Unsupported language", to=sid)
        return

    # Fork a new pseudo-terminal process to run the command.
    pid, fd = pty.fork()
    if pid == 0:
        try:
            os.execvp(command[0], command)
        except Exception as e:
            print("Error executing command:", e)
            os._exit(1)
    else:
        terminals[sid] = {'fd': fd, 'cleanup': cleanup}

        def read_from_fd(sid, fd):
            """Continuously read from the pty and stream the output to the client."""
            while True:
                try:
                    r, _, _ = select.select([fd], [], [], 0.1)
                    if fd in r:
                        output = os.read(fd, 1024)
                        if not output:
                            break
                        decoded = output.decode('utf-8', errors='ignore')
                        socketio.emit('output', decoded, to=sid)
                except Exception as e:
                    print("Error reading from fd:", e)
                    break

        thread = threading.Thread(target=read_from_fd, args=(sid, fd))
        thread.daemon = True
        thread.start()

@socketio.on('input')
def handle_input(data):
    """Handle interactive input from the client and write it to the running process."""
    sid = request.sid
    info = terminals.get(sid)
    if info:
        try:
            os.write(info['fd'], data.encode())
        except Exception as e:
            print("Error writing to fd:", e)

@socketio.on('disconnect')
def handle_disconnect():
    """Clean up process information when the client disconnects."""
    sid = request.sid
    info = terminals.pop(sid, None)
    if info:
        try:
            os.close(info['fd'])
        except Exception:
            pass
        try:
            info['cleanup']()
        except Exception:
            pass

if __name__ == '__main__':
    socketio.run(app, debug=True)
