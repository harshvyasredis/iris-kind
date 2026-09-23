#!/bin/bash
set -euo pipefail

start_dev() {
  if [ -f /app/package.json ]; then
    npm install
    npm run dev
  else
    echo "No package.json in /app; terminal-only pack"
    exec bash
  fi
}

create_session() {
  tmux -f /etc/tmux.conf new-session -d -s workshop -c /app
  if [ -f /app/package.json ]; then
    tmux send-keys -t workshop 'npm install' Enter
    tmux send-keys -t workshop 'npm run dev' Enter
  fi
}

if ! tmux has-session -t workshop 2>/dev/null; then
  create_session
fi

ttyd -W -p 7681 bash -c '
  if ! tmux -f /etc/tmux.conf has-session -t workshop 2>/dev/null; then
    tmux -f /etc/tmux.conf new-session -d -s workshop -c /app
    if [ -f /app/package.json ]; then
      tmux send-keys -t workshop "npm install" Enter
      tmux send-keys -t workshop "npm run dev" Enter
    fi
  fi
  exec tmux -f /etc/tmux.conf attach-session -t workshop
'
