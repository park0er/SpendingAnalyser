const { app, BrowserWindow, dialog } = require('electron');
const { spawn } = require('child_process');
const http = require('http');
const net = require('net');
const path = require('path');
const fs = require('fs');

let backendProcess = null;
let mainWindow = null;

function ensureDir(dir) {
  fs.mkdirSync(dir, { recursive: true });
}

function getFreePort() {
  return new Promise((resolve, reject) => {
    const server = net.createServer();
    server.listen(0, '127.0.0.1', () => {
      const { port } = server.address();
      server.close(() => resolve(port));
    });
    server.on('error', reject);
  });
}

function resourcePath(...parts) {
  if (app.isPackaged) {
    return path.join(process.resourcesPath, ...parts);
  }
  return path.join(__dirname, '..', ...parts);
}

function waitForBackend(port, timeoutMs = 45000) {
  const started = Date.now();
  return new Promise((resolve, reject) => {
    const check = () => {
      const req = http.get(`http://127.0.0.1:${port}/api/health`, (res) => {
        res.resume();
        if (res.statusCode === 200) {
          resolve();
        } else {
          retry();
        }
      });
      req.on('error', retry);
      req.setTimeout(1200, () => {
        req.destroy();
        retry();
      });
    };

    const retry = () => {
      if (Date.now() - started > timeoutMs) {
        reject(new Error('Backend did not become ready in time.'));
        return;
      }
      setTimeout(check, 500);
    };

    check();
  });
}

function createWindow() {
  mainWindow = new BrowserWindow({
    width: 1440,
    height: 980,
    minWidth: 1040,
    minHeight: 720,
    title: 'SpendingAnalyser',
    backgroundColor: '#0f1117',
    show: false,
    webPreferences: {
      contextIsolation: true,
      nodeIntegration: false,
    },
  });

  mainWindow.once('ready-to-show', () => {
    mainWindow.show();
  });

  mainWindow.on('closed', () => {
    mainWindow = null;
  });
}

async function startBackend(port) {
  const userData = app.getPath('userData');
  const dataDir = path.join(userData, 'data');
  const outputDir = path.join(userData, 'output');
  const configPath = path.join(userData, 'config.env');
  ensureDir(dataDir);
  ensureDir(outputDir);

  const env = {
    ...process.env,
    SPENDING_DESKTOP: '1',
    PORT: String(port),
    DATA_DIR: dataDir,
    OUTPUT_DIR: outputDir,
    CONFIG_PATH: configPath,
    FRONTEND_DIR: resourcePath('frontend'),
  };

  if (app.isPackaged) {
    const backendPath = resourcePath('backend', 'spending-backend', 'spending-backend');
    const logPath = path.join(userData, 'backend.log');
    const log = fs.openSync(logPath, 'a');
    backendProcess = spawn(backendPath, [], { env, stdio: ['ignore', log, log] });
  } else {
    backendProcess = spawn('python3', ['-m', 'src.api'], {
      cwd: path.join(__dirname, '..'),
      env,
      stdio: 'inherit',
    });
  }

  backendProcess.on('exit', (code) => {
    if (code !== 0 && mainWindow) {
      dialog.showErrorBox('SpendingAnalyser 后端已停止', `退出码：${code}`);
    }
  });
}

async function boot() {
  createWindow();
  mainWindow.loadURL(`data:text/html;charset=utf-8,${encodeURIComponent('<body style="margin:0;background:#0f1117;color:#e8eaf0;font:16px -apple-system,BlinkMacSystemFont,sans-serif;display:grid;place-items:center;height:100vh">SpendingAnalyser 正在启动...</body>')}`);

  const port = await getFreePort();
  await startBackend(port);
  await waitForBackend(port);
  await mainWindow.loadURL(`http://127.0.0.1:${port}`);
}

app.whenReady().then(() => {
  boot().catch((error) => {
    dialog.showErrorBox('SpendingAnalyser 启动失败', error.message);
    app.quit();
  });
});

app.on('window-all-closed', () => {
  app.quit();
});

app.on('before-quit', () => {
  if (backendProcess && !backendProcess.killed) {
    backendProcess.kill();
  }
});
