#!/bin/bash
# SpendingAnalyser 一键启动脚本

cd "$(dirname "$0")"

echo "🔄 清理旧进程..."
pkill -f "from src.api" 2>/dev/null
pkill -f "flask" 2>/dev/null
lsof -ti:5001 | xargs kill 2>/dev/null
sleep 1

echo "🚀 启动 Flask 后端 (端口 5001)..."
nohup /Library/Developer/CommandLineTools/usr/bin/python3 -c "
import sys, os
sys.path.insert(0, '.')
os.environ['DATA_DIR'] = 'data'
os.environ['OUTPUT_DIR'] = 'output'
from src.api import app
app.run(host='0.0.0.0', port=5001)
" > /tmp/spending_flask.log 2>&1 &
FLASK_PID=$!
echo "   Flask PID: $FLASK_PID"

sleep 2

# 检查 Flask 是否启动成功
if curl -s http://localhost:5001/api/summary > /dev/null 2>&1; then
  echo "   ✅ Flask 后端启动成功"
else
  echo "   ⏳ Flask 正在处理数据，请稍等..."
  sleep 5
  if curl -s http://localhost:5001/api/summary > /dev/null 2>&1; then
    echo "   ✅ Flask 后端启动成功"
  else
    echo "   ⚠️  Flask 可能还在启动中，请检查 /tmp/spending_flask.log"
  fi
fi

echo ""
echo "🚀 启动 Vite 前端..."
cd frontend
nohup ./node_modules/.bin/vite --port 3001 > /tmp/spending_vite.log 2>&1 &
VITE_PID=$!
echo "   Vite PID: $VITE_PID"
sleep 2
echo ""

echo "============================================"
echo "✅ 全部启动完成！"
echo "   前端: http://localhost:3001"
echo "   后端: http://localhost:5001/api/summary"
echo ""
echo "   停止服务: kill $FLASK_PID $VITE_PID"
echo "============================================"
