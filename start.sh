#!/usr/bin/env bash

set -e

PROJECT_DIR=$(cd "$(dirname "$0")" && pwd)
cd "$PROJECT_DIR"

if [ ! -d "venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv venv
fi

source venv/bin/activate

python -m pip install --upgrade pip

if [ -f requirements.txt ]; then
    pip install -r requirements.txt
fi

if [ ! -f .env ]; then
    echo "Missing .env file"
    echo "Please copy .env.example to .env and configure LLM/Feishu settings"
    exit 1
fi

python scripts/verify.py
python -m app.cli check

python -m app.cli
