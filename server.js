// server.js
const express = require('express');
const http = require('http');
const path = require('path');
const fs = require('fs');
const tmp = require('tmp');
const { spawn, execSync, exec } = require('child_process');
const pty = require('node-pty');
const { Server } = require('socket.io');

const app = express();
const server = http.createServer(app);
const io = new Server(server);

// Serve the index.html file
app.use(express.static(path.join(__dirname, 'public')));

const terminals = {}; // Store per-session pty processes and cleanup functions

// Helper to run a command and capture output synchronously (for compilation)
function runCommandSync(command, args, cwd) {
  try {
    // execSync returns a Buffer. Convert to string.
    const result = execSync([command, ...args].join(' '), { cwd, stdio: 'pipe' });
    return { success: true, output: result.toString() };
  } catch (error) {
    return { success: false, output: error.stderr ? error.stderr.toString() : error.message };
  }
}

io.on('connection', (socket) => {
  console.log(`Client connected: ${socket.id}`);

  socket.on('run_code', (data) => {
    // If a previous session exists, cleanup.
    if (terminals[socket.id]) {
      try { terminals[socket.id].ptyProcess.kill(); } catch (e) {}
      try { terminals[socket.id].cleanup(); } catch (e) {}
      delete terminals[socket.id];
    }

    let { language, code } = data;
    language = language || 'python';

    let command, args = [], cleanup = () => {}; // Default no-op cleanup

    if (language === 'python') {
      // Create a temporary file for python script.
      const tmpFile = tmp.fileSync({ postfix: '.py' });
      fs.writeFileSync(tmpFile.name, code);
      cleanup = () => tmpFile.removeCallback();
      command = 'python3';
      args = ['-u', tmpFile.name];

    } else if (language === 'java') {
      // Create a temporary directory and write Main.java.
      const tmpDir = tmp.dirSync({ unsafeCleanup: true });
      const filePath = path.join(tmpDir.name, 'Main.java');
      fs.writeFileSync(filePath, code);
      // Compile the java file.
      let compileResult = runCommandSync('javac', ['Main.java'], tmpDir.name);
      if (!compileResult.success) {
        socket.emit('output', compileResult.output);
        tmpDir.removeCallback();
        return;
      }
      cleanup = () => tmpDir.removeCallback();
      command = 'java';
      args = ['-cp', tmpDir.name, 'Main'];

    } else if (language === 'c') {
      // Create a temporary directory and write main.c.
      const tmpDir = tmp.dirSync({ unsafeCleanup: true });
      const filePath = path.join(tmpDir.name, 'main.c');
      fs.writeFileSync(filePath, code);
      // Compile the c file.
      let compileResult = runCommandSync('gcc', ['main.c', '-o', 'main_exe'], tmpDir.name);
      if (!compileResult.success) {
        socket.emit('output', compileResult.output);
        tmpDir.removeCallback();
        return;
      }
      cleanup = () => tmpDir.removeCallback();
      command = path.join(tmpDir.name, 'main_exe');
      args = [];

    } else if (language === 'c++') {
      // Create a temporary directory and write main.cpp.
      const tmpDir = tmp.dirSync({ unsafeCleanup: true });
      const filePath = path.join(tmpDir.name, 'main.cpp');
      fs.writeFileSync(filePath, code);
      // Compile the C++ file.
      let compileResult = runCommandSync('g++', ['main.cpp', '-o', 'main_exe'], tmpDir.name);
      if (!compileResult.success) {
        socket.emit('output', compileResult.output);
        tmpDir.removeCallback();
        return;
      }
      cleanup = () => tmpDir.removeCallback();
      command = path.join(tmpDir.name, 'main_exe');
      args = [];

    } else if (language === 'javascript') {
      // Create a temporary file for JavaScript.
      const tmpFile = tmp.fileSync({ postfix: '.js' });
      fs.writeFileSync(tmpFile.name, code);
      cleanup = () => tmpFile.removeCallback();
      command = 'node';
      args = [tmpFile.name];

    } else if (language === 'php') {
      // Create a temporary file for PHP.
      const tmpFile = tmp.fileSync({ postfix: '.php' });
      fs.writeFileSync(tmpFile.name, code);
      cleanup = () => tmpFile.removeCallback();
      command = 'php';
      args = ['-f', tmpFile.name];

    } else if (language === 'perl') {
      // Create a temporary file for Perl.
      const tmpFile = tmp.fileSync({ postfix: '.pl' });
      fs.writeFileSync(tmpFile.name, code);
      cleanup = () => tmpFile.removeCallback();
      command = 'perl';
      args = [tmpFile.name];

    } else {
      socket.emit('output', 'Unsupported language');
      return;
    }

    // Start the process in a pseudo-terminal
    const ptyProcess = pty.spawn(command, args, {
      name: 'xterm-color',
      cols: 80,
      rows: 30,
      cwd: process.cwd(),
      env: process.env,
    });

    terminals[socket.id] = { ptyProcess, cleanup };

    // Send output as it arrives.
    ptyProcess.on('data', (data) => {
      socket.emit('output', data);
    });

    // When the process exits, clean up.
    ptyProcess.on('exit', () => {
      socket.emit('output', '\nProcess exited.');
      if (terminals[socket.id]) {
        terminals[socket.id].cleanup();
        delete terminals[socket.id];
      }
    });
  });

  socket.on('input', (data) => {
    if (terminals[socket.id]) {
      terminals[socket.id].ptyProcess.write(data);
    }
  });

  socket.on('disconnect', () => {
    if (terminals[socket.id]) {
      try { terminals[socket.id].ptyProcess.kill(); } catch (e) {}
      try { terminals[socket.id].cleanup(); } catch (e) {}
      delete terminals[socket.id];
    }
  });
});

const PORT = 3000;
server.listen(PORT, () => {
  console.log(`Server is running on port ${PORT}`);
});

