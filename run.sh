#!/bin/bash

echo "🚀 Запускаю Discord-бота..."
python3 bot.py &

echo "🌐 Запускаю Flask-сайт через Gunicorn..."
gunicorn -w 2 -b 127.0.0.1:5000 site:app