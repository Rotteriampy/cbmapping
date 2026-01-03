#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Discord Bot для мониторинга серверов и сбора статистики
Запускается отдельно от Flask-сервера
"""

import discord
from discord.ext import commands, tasks
import json
import os
import time
from datetime import datetime
from collections import defaultdict
from dotenv import load_dotenv

# ===== НАСТРОЙКИ =====
load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "servers")
ASSETS_DIR = os.path.join(BASE_DIR, "servers", "assets")

# Создаём папки
os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(ASSETS_DIR, exist_ok=True)

# ===== БОТ =====
intents = discord.Intents.default()
intents.guilds = True
intents.members = True
intents.presences = True
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents, help_command=None)

# Глобальные данные
servers_data = {}
last_update = {}

# ===== ФУНКЦИИ =====
async def fetch_server_info(guild: discord.Guild):
    """Получает информацию о сервере и участников"""
    try:
        online_count = sum(1 for m in guild.members if m.status != discord.Status.offline)
        guild_id = str(guild.id)

        # Загрузка аватарки
        icon_filename = f"{guild_id}_icon.png"
        icon_path = os.path.join(ASSETS_DIR, icon_filename)
        if guild.icon and not os.path.exists(icon_path):
            try:
                icon_bytes = await guild.icon.read()
                with open(icon_path, "wb") as f:
                    f.write(icon_bytes)
            except Exception as e:
                print(f"Ошибка загрузки аватарки {guild.name}: {e}")

        # Загрузка баннера
        banner_filename = f"{guild_id}_banner.png"
        banner_path = os.path.join(ASSETS_DIR, banner_filename)
        if guild.banner and not os.path.exists(banner_path):
            try:
                banner_bytes = await guild.banner.read()
                with open(banner_path, "wb") as f:
                    f.write(banner_bytes)
            except Exception as e:
                print(f"Ошибка загрузки баннера {guild.name}: {e}")

        premium_tier = guild.premium_tier
        premium_subscription_count = guild.premium_subscription_count or 0

        info = {
            "id": guild_id,
            "name": guild.name,
            "member_count": guild.member_count,
            "online_count": online_count,
            "description": guild.description or "Нет описания",
            "created_at": guild.created_at.timestamp() if guild.created_at else None,
            "icon_url": f"assets/{icon_filename}" if os.path.exists(icon_path) else None,
            "banner_url": f"assets/{banner_filename}" if os.path.exists(banner_path) else None,
            "owner_id": str(guild.owner_id) if guild.owner else None,
            "premium_tier": premium_tier,
            "premium_subscription_count": premium_subscription_count,
        }

        info.update({
            "created_at": guild.created_at.strftime("%d.%m.%Y") if guild.created_at else None,
            "owner": str(guild.owner) if guild.owner else None,
            "features": guild.features,  # Например: VERIFIED, PARTNERED и т.д.
            "vanity_url": guild.vanity_url_code,
        })

        members = []
        for member in guild.members:
            members.append({
                "id": str(member.id),
                "name": member.display_name,
                "bot": member.bot,
                "status": str(member.status),
                "joined_at": member.joined_at.timestamp() if member.joined_at else None
            })

        return info, members
    except Exception as e:
        print(f"Ошибка получения данных {guild.name}: {e}")
        return None, []

def analyze_member_overlaps(current_guild_id, current_members):
    """Анализирует пересечения участников"""
    overlaps = {}
    current_member_ids = {m["id"] for m in current_members if not m.get("bot", False)}

    for other_guild_id, other_data in servers_data.items():
        if other_guild_id == current_guild_id:
            continue
        other_members = other_data.get("members", [])
        other_member_ids = {m["id"] for m in other_members if not m.get("bot", False)}
        common_members = current_member_ids & other_member_ids
        if common_members:
            other_info = other_data.get("info", {})
            overlaps[other_guild_id] = {
                "server_name": other_info.get("name", "Unknown"),
                "common_count": len(common_members),
                "common_member_ids": list(common_members)
            }
    return overlaps

async def update_server_data(guild: discord.Guild):
    """Обновляет данные одного сервера"""
    info, members = await fetch_server_info(guild)
    if not info:
        return

    guild_id = str(guild.id)
    current_time = time.time()

    if guild_id not in servers_data:
        servers_data[guild_id] = {"info": info, "history": [], "members": members}

    servers_data[guild_id]["history"].append({
        "timestamp": current_time,
        "member_count": info["member_count"],
        "online_count": info["online_count"]
    })
    servers_data[guild_id]["info"] = info
    servers_data[guild_id]["members"] = members
    last_update[guild_id] = current_time

    # Сохраняем в JSON
    json_file = os.path.join(DATA_DIR, f"{guild_id}.json")
    with open(json_file, "w", encoding="utf-8") as f:
        json.dump(servers_data[guild_id], f, ensure_ascii=False, indent=2)

    print(f"Обновлено: {guild.name}")

@tasks.loop(minutes=1)
async def auto_update():
    """Автоматическое обновление каждую минуту"""
    for guild in bot.guilds:
        await update_server_data(guild)

    # Пересчёт пересечений
    for guild_id, data in servers_data.items():
        members = data.get("members", [])
        servers_data[guild_id]["member_overlaps"] = analyze_member_overlaps(guild_id, members)
        json_file = os.path.join(DATA_DIR, f"{guild_id}.json")
        with open(json_file, "w", encoding="utf-8") as f:
            json.dump(servers_data[guild_id], f, ensure_ascii=False, indent=2)

# ===== СОБЫТИЯ =====
@bot.event
async def on_ready():
    print(f"Бот запущен: {bot.user} ({bot.user.id})")
    print(f"Серверов: {len(bot.guilds)}")

    # Первое обновление
    for guild in bot.guilds:
        await update_server_data(guild)

    # Пересчёт пересечений
    for guild_id, data in servers_data.items():
        members = data.get("members", [])
        servers_data[guild_id]["member_overlaps"] = analyze_member_overlaps(guild_id, members)

    auto_update.start()
    print("Автообновление запущено")

@bot.event
async def on_guild_join(guild):
    print(f"Добавлен на сервер: {guild.name}")
    await update_server_data(guild)

# ===== ЗАПУСК =====
if __name__ == "__main__":
    try:
        bot.run(TOKEN)
    except KeyboardInterrupt:
        print("\nБот остановлен")