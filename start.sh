#!/bin/bash
# ═══════════════════════════════════════════════════
# SpendingAnalyser 一键启动脚本
# ═══════════════════════════════════════════════════
# 首次运行会自动安装依赖。之后每次启动约 3 秒。
# 使用方式：  chmod +x start.sh && ./start.sh
# 停止服务：  ./start.sh stop

cd "$(dirname "$0")"
PROJECT_DIR=$(pwd)

# ── 停止命令 ──────────────────────────────────────
if [ "$1" = "stop" ]; then
    echo "🛑 正在停止服务..."
    pkill -f "from src.api" 2>/dev/null
    lsof -ti:5001 | xargs kill 2>/dev/null
    lsof -ti:3001 | xargs kill 2>/dev/null
    echo "✅ 已停止"
    exit 0
fi

# ── 检查 Python ───────────────────────────────────
PYTHON=""
if command -v python3 &>/dev/null; then
    PYTHON="python3"
elif command -v python &>/dev/null; then
    PYTHON="python"
else
    echo "❌ 未找到 Python。请先安装 Python 3.9+。"
    echo "   Mac: brew install python3"
    exit 1
fi
echo "🐍 Python: $($PYTHON --version)"

# ── 检查 Node.js ──────────────────────────────────
if ! command -v node &>/dev/null; then
    echo "❌ 未找到 Node.js。请先安装 Node.js 18+。"
    echo "   Mac: brew install node"
    exit 1
fi
echo "📦 Node: $(node --version)"

# ── 首次安装 Python 依赖 ─────────────────────────
if ! $PYTHON -c "import flask" 2>/dev/null; then
    echo ""
    echo "📦 首次运行，正在安装 Python 依赖..."
    $PYTHON -m pip install -r requirements.txt --quiet
    echo "   ✅ Python 依赖安装完成"
fi

# ── 首次安装前端依赖 ──────────────────────────────
if [ ! -d "frontend/node_modules" ]; then
    echo ""
    echo "📦 首次运行，正在安装前端依赖..."
    cd frontend && npm install --silent && cd ..
    echo "   ✅ 前端依赖安装完成"
fi

# ── 检查数据目录 ──────────────────────────────────
if [ ! -d "data" ]; then
    mkdir -p data
    echo ""
    echo "📁 已创建 data/ 目录。请将交易账单 CSV 文件放入此目录："
    echo "   - 支付宝: 支付宝交易明细(XXXXXXXX-XXXXXXXX).csv"
    echo "   - 微信:   微信支付账单(XXXXXXXX-XXXXXXXX).csv"
    echo "   - 京东:   京东交易流水*.csv"
    echo "   - 美团:   美团账单*.csv"
    echo ""
    echo "   放好文件后重新运行 ./start.sh"
    exit 0
fi

# ── 检查 config.env ───────────────────────────────
if [ ! -f "config.env" ]; then
    echo ""
    echo "📋 未找到 config.env，正在创建配置模板..."
    cat > config.env << 'EOF'
# ──────────────────────────────────────────────
# SpendingAnalyser LLM 配置文件
# ──────────────────────────────────────────────
# 用于 LLM 自动打标功能。首次使用前请填写以下配置。

# API Key（从模型服务商控制台获取）
LLM_API_KEY=在此填写你的API密钥

# API Base URL（兼容 Anthropic 格式的接口地址）
LLM_BASE_URL=https://api.xiaomimimo.com/anthropic

# 模型名称
LLM_MODEL=mimo-v2.5-pro
EOF
    echo "   ⚠️  请编辑 config.env 填写你的 API Key，然后重新运行 ./start.sh"
    exit 0
fi

# ── 创建输出目录 ──────────────────────────────────
mkdir -p output

# ── 清理旧进程 ────────────────────────────────────
echo ""
echo "🔄 清理旧进程..."
pkill -f "from src.api" 2>/dev/null
lsof -ti:5001 | xargs kill 2>/dev/null
lsof -ti:3001 | xargs kill 2>/dev/null
sleep 1

# ── 运行数据处理 Pipeline ────────────────────────
echo ""
echo "📊 运行数据处理 Pipeline..."
$PYTHON -m src.main data

# ── 启动 Flask 后端 ──────────────────────────────
echo ""
echo "🚀 启动 Flask 后端 (端口 5001)..."
nohup $PYTHON -c "
import sys, os
sys.path.insert(0, '.')
os.environ['DATA_DIR'] = 'data'
os.environ['OUTPUT_DIR'] = 'output'
from src.api import app
app.run(host='0.0.0.0', port=5001)
" > /tmp/spending_flask.log 2>&1 &
FLASK_PID=$!

sleep 2

# 检查 Flask 是否启动成功
if curl -s http://localhost:5001/api/summary > /dev/null 2>&1; then
    echo "   ✅ Flask 后端启动成功 (PID: $FLASK_PID)"
else
    echo "   ⏳ Flask 正在处理数据，请稍等..."
    sleep 5
    if curl -s http://localhost:5001/api/summary > /dev/null 2>&1; then
        echo "   ✅ Flask 后端启动成功 (PID: $FLASK_PID)"
    else
        echo "   ⚠️  Flask 可能还在启动中，请检查 /tmp/spending_flask.log"
    fi
fi

# ── 启动 Vite 前端 ───────────────────────────────
echo ""
echo "🚀 启动 Vite 前端 (端口 3001)..."
cd frontend
nohup ./node_modules/.bin/vite --port 3001 > /tmp/spending_vite.log 2>&1 &
VITE_PID=$!
cd ..
sleep 2

echo ""
echo "════════════════════════════════════════════════"
echo "✅ 全部启动完成！"
echo ""
echo "   🌐 前端:  http://localhost:3001"
echo "   🔌 后端:  http://localhost:5001/api/summary"
echo ""
echo "   停止服务:  ./start.sh stop"
echo "   LLM 打标:  $PYTHON src/classifiers/llm_tagger_runner.py"
echo "════════════════════════════════════════════════"

# 尝试自动打开浏览器
if command -v open &>/dev/null; then
    open "http://localhost:3001"
elif command -v xdg-open &>/dev/null; then
    xdg-open "http://localhost:3001"
fi
