# run.ps1
Write-Host "🚀 Запускаю Discord-бота..."
Start-Process -NoNewWindow -FilePath python -ArgumentList "bot.py"

Write-Host "🌐 Запускаю Flask-сайт на http://0.0.0.0:5000"
python site.py