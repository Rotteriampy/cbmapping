from flask import Flask, render_template, request, abort, send_from_directory, url_for, make_response, flash, session, redirect
import json
import os
import html as html_module
import markdown
from datetime import datetime
import re
import glob
import subprocess
import sys
import secrets
import time
from dotenv import load_dotenv

load_dotenv()
app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY")
JSON_DIR = "static/img"

# =========================
# Sitemap.xml
# =========================

@app.route("/sitemap.xml")
def sitemap():
    static_pages = [
        "",
        "/index",
        "/wiki",
        "/servers",
        "/guides",
        "/materials",
        "/info",
    ]

    urls = set(static_pages)

    # ---- Серверы
    for slug in server_slug_cache.keys():
        urls.add(f"/server/{slug}")

    for guild_id in servers_data.keys():
        if guild_id.isdigit():
            urls.add(f"/server/{guild_id}")

    # ---- Wiki страницы
    for item in orgs + persons + events:
        item_id = item.get("id")
        name = item.get("name")

        if not item_id:
            continue

        slug = slugify(name) if name else ""
        urls.add(f"/wiki/{slug or item_id}")

    base_url = request.url_root.rstrip("/")

    xml = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
    ]

    today = datetime.utcnow().date().isoformat()

    for url in sorted(urls):
        full_url = f"{base_url}{url}"

        if url == "/info":
            priority = "1.0"
            changefreq = "yearly"
        elif url.startswith("/wiki/"):
            priority = "0.9"
            changefreq = "weekly"
        else:
            priority = "0.6"
            changefreq = "daily"

        xml.extend([
            "  <url>",
            f"    <loc>{full_url}</loc>",
            f"    <lastmod>{today}</lastmod>",
            f"    <changefreq>{changefreq}</changefreq>",
            f"    <priority>{priority}</priority>",
            "  </url>"
        ])

    xml.append("</urlset>")

    response = make_response("\n".join(xml))
    response.headers["Content-Type"] = "application/xml"
    return response

# Путь к папке с данными серверов (JSON)
SERVERS_DATA_DIR = os.path.join(app.root_path, 'servers')

# Путь к папке с аватарками и баннерами (куда бот сохраняет)
ASSETS_DIR = os.path.join(app.root_path, 'servers', 'assets')

# Глобальная переменная для данных серверов
servers_data = {}

def load_servers_data():
    """Загружает все JSON-файлы серверов из папки servers/"""
    global servers_data
    servers_data = {}
    json_files = glob.glob(os.path.join(SERVERS_DATA_DIR, "*.json"))
    for file_path in json_files:
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                guild_id = os.path.basename(file_path).replace('.json', '')
                servers_data[guild_id] = data
            print(f"Загружен сервер: {data.get('info', {}).get('name', guild_id)}")
        except Exception as e:
            print(f"Ошибка загрузки {file_path}: {e}")

# Загружаем при старте
load_servers_data()

# Путь к данным вики
DATA_FOLDER = os.path.join(app.root_path, 'pages_data')
DATA_PAGES_DIR = os. path.join(app.root_path, 'pages_data')

def load_json(filename):
    filepath = os.path.join(DATA_FOLDER, filename)
    if not os.path.exists(filepath):
        print(f"Warning: Файл {filepath} не найден!")
        return []
    with open(filepath, 'r', encoding='utf-8') as f:
        return json.load(f)

orgs = load_json('organizations.json')
persons = load_json('personalities.json')
events = load_json('events.json')

# === ИСПРАВЛЕННЫЙ МАРШРУТ ДЛЯ ИКОНОК ===
@app.route('/servers/assets/<path:filename>')
def server_assets(filename):
    """
    Отдаёт аватарки и баннеры из servers/assets/
    Теперь путь /servers/assets/1119578507287220324_icon.png работает!
    """
    return send_from_directory(ASSETS_DIR, filename)

# Границы слайдеров
MIN_YEAR = 2017
MAX_YEAR = 2025
try:
    max_members = max(int(org.get('peak_members', 0) or 0) for org in orgs if org.get('peak_members'))
    MAX_MEMBERS = max(max_members, 935)
except:
    MAX_MEMBERS = 935

def slugify(text):
    """Создаёт красивый slug из названия"""
    if not text:
        return ""
    text = str(text).lower()
    text = re.sub(r'[^а-яa-z0-9\s-]+', '', text)
    text = re.sub(r'\s+', '-', text)
    text = re.sub(r'-+', '-', text)
    return text.strip('-')

def find_item_by_slug_or_id(query):
    """Ищет элемент по slug (из name) или по id"""
    all_data = [('org', orgs), ('person', persons), ('event', events)]
    for item_type, source in all_data:
        for item in source:
            if str(item.get('id')) == query:
                return item, item_type
            name_slug = slugify(item.get('name', ''))
            if name_slug == query:
                return item, item_type
    return None, None

def get_gallery_images_cached(item_id, type_key):
    """
    Возвращает список уникальных изображений из папки static/img/wiki/<type_folder>/<item_id>/
    Без дубликатов по регистру расширения
    """
    if not item_id or not type_key:
        return []

    type_folder_map = {
        'org': 'organization',
        'person': 'personalities',
        'event': 'events'
    }
    folder_type = type_folder_map.get(type_key, 'events')

    folder_path = os.path.join(app.static_folder, 'img', 'wiki', folder_type, str(item_id))
    
    if not os.path.exists(folder_path):
        return []

    # Ищем только по строчным расширениям — этого достаточно (Windows нечувствителен к регистру)
    extensions = ['*.jpg', '*.jpeg', '*.png', '*.gif', '*.webp']
    images = []
    seen_files = set()  # Для дополнительной защиты от дублей

    for ext in extensions:
        pattern = os.path.join(folder_path, ext)
        for file_path in glob.glob(pattern):
            filename = os.path.basename(file_path).lower()  # Приводим к нижнему регистру для сравнения
            if filename in seen_files:
                continue
            seen_files.add(filename)

            rel_url = f"/static/img/wiki/{folder_type}/{item_id}/{os.path.basename(file_path)}"
            images.append({
                'url': rel_url,
                'original': os.path.basename(file_path)
            })
    
    # Сортируем по оригинальному имени файла (с сохранением регистра)
    images.sort(key=lambda x: x['original'].lower())
    
    return images

@app.route("/")
@app.route("/index")
def index():
    return render_template("index.html")

@app.route("/wiki")
def wiki():
    return render_template(
        "wiki.html",
        orgs_json=orgs,
        persons_json=persons,
        events_json=events,
        min_year_bound=MIN_YEAR,
        max_year_bound=MAX_YEAR,
        max_members_bound=MAX_MEMBERS
    )

@app.route("/wiki/<path:slug>")
def wiki_detail(slug):
    item, item_type = find_item_by_slug_or_id(slug)
    if not item:
        abort(404)

    item_id = item.get('id')

    # === Генерация данных для шаблона ===
    def calculate_timespan(start, end=None):
        if not start:
            return "Неизвестно"
        try:
            if end and end != 'null':
                end_display = end
            else:
                end_display = "наст. время"
            return f"{start} – {end_display}"
        except:
            return f"{start} – {end or 'наст. время'}"

    item_name = html_module.escape(item.get("name", "Unknown"))
    description_safe = markdown.markdown(
        item.get("description", ""),
        extensions=[
            'markdown.extensions.extra',
            'markdown.extensions.nl2br',
            'pymdownx.magiclink'
        ]
    )

    # Галерея
    avatar_urls = []
    if item_type in ('org', 'person'):
        avatar_urls = get_gallery_images_cached(item_id, item_type)

    avatar_list_html = ""
    for img in avatar_urls:
        safe_url = html_module.escape(img.get('url', ''))
        safe_name = html_module.escape(img.get('original', ''))
        avatar_list_html += f'''
            <div class="gallery-item clickable-avatar" data-src="{safe_url}" title="{safe_name}">
                <img src="{safe_url}" alt="{safe_name}" loading="lazy">
            </div>
        '''
    avatar_gallery_html = f'''
        <div class="media-gallery-block">
            <h2 class="gallery-title">Медиа ({len(avatar_urls)})</h2>
            <div class="gallery-list">
                {avatar_list_html or '<p style="color: rgba(255,255,255,0.6);">Нет изображений</p>'}
            </div>
        </div>
    ''' if avatar_urls else ''

    # Таблица
    item_fields_html = ""
    translation_map = {'leader': 'Лидеры', 'peak_members': 'Пик участников', 'old_nicknames': 'Старые ники'}

    def get_social_icon(url):
        url = str(url).lower()
        if "discord" in url: return "Discord", "#5865F2"
        if "youtube" in url or "youtu.be" in url: return "YouTube", "#FF0000"
        if "t.me" in url: return "Telegram", "#2AABEE"
        if "vk.com" in url: return "VK", "#0077FF"
        if "github" in url: return "GitHub", "#181717"
        return "Ссылка", "#6c757d"

    # Типовые поля
    if item_type == 'org':
        timespan = calculate_timespan(item.get("created"), item.get("closed"))
        item_fields_html += f"<tr><td>Время существования</td><td>{html_module.escape(timespan)}</td></tr>"
        if item.get("closed"):
            reason = item.get("reason_for_closing") or "Не указана"
            item_fields_html += f"<tr><td>Причина закрытия</td><td>{html_module.escape(reason)}</td></tr>"

    elif item_type == 'person':
        timespan = calculate_timespan(item.get("created"), item.get("departed"))
        item_fields_html += f"<tr><td>Время в комьюнити</td><td>{html_module.escape(timespan)}</td></tr>"
        socials = item.get("social_media") or item.get("links") or []
        if socials:
            buttons = ""
            for link in socials:
                icon, color = get_social_icon(link)
                safe_link = html_module.escape(link)
                buttons += f'<a href="{safe_link}" target="_blank" class="social-button" style="background-color:{color};">{icon}</a>'
            item_fields_html += f"<tr><td>Соцсети</td><td><div class='social-buttons-wrap'>{buttons}</div></td></tr>"

    elif item_type == 'event':
        if item.get("event_type"):
            item_fields_html += f"<tr><td>Тип ивента</td><td>{html_module.escape(item.get('event_type'))}</td></tr>"
        if item.get("date"):
            item_fields_html += f"<tr><td>Дата ивента</td><td>{html_module.escape(item.get('date'))}</td></tr>"

    # Остальные поля
    skip_keys = ['id', 'name', 'description', 'created', 'closed', 'departed', 'date', 'links', 'social_media', 'event_type', 'reason_for_closing', 'avatar_url']
    for key, value in item.items():
        if key in skip_keys or value in (None, "", []):
            continue
        label = translation_map.get(key, key.replace('_', ' ').capitalize())

        if key == 'leader' and value:
            if isinstance(value, list): value = ", ".join(map(str, value))
            rendered = markdown.markdown(str(value), extensions=['extra', 'nl2br'])
            if rendered.strip() != '<p></p>':
                item_fields_html += f"<tr><td>{label}</td><td class='scrollable-cell'>{rendered}</td></tr>"
            continue

        if isinstance(value, list):
            val = "<br>".join(html_module.escape(str(v)) for v in value)
        else:
            val = html_module.escape(str(value))
        item_fields_html += f"<tr><td>{label}</td><td class='scrollable-cell'>{val}</td></tr>"

    return render_template(
        "wikipage.html",
        item_name=item_name,
        item_description_safe=description_safe,
        item_fields_html=item_fields_html,
        avatar_gallery_html=avatar_gallery_html
    )

@app.route("/servers")
def servers():
    sorted_servers = sorted(
        servers_data.items(),
        key=lambda x: x[1].get("info", {}).get("name", "").lower()
    )
    
    return render_template(
        "servers.html",
        servers=sorted_servers,
        total_servers=len(servers_data)
    )

# Кэш для slug → guild_id (чтобы быстро находить по названию)
server_slug_cache = {}

def generate_server_slug(name, guild_id):
    """Генерирует slug из названия. Если не уникально — возвращает ID"""
    if not name:
        return str(guild_id)
    
    # Транслит + безопасные символы
    slug = re.sub(r'[^a-z0-9\-_]', '-', name.lower())
    slug = re.sub(r'-+', '-', slug).strip('-')
    
    if not slug:
        return str(guild_id)
    
    # Если slug свободен — используем его
    if slug not in server_slug_cache:
        server_slug_cache[slug] = guild_id
        return slug
    else:
        # Если занят — fallback на ID
        return str(guild_id)

def load_servers_data():
    global servers_data, server_slug_cache
    servers_data = {}
    server_slug_cache = {}
    json_files = glob.glob(os.path.join(SERVERS_DATA_DIR, "*.json"))
    for file_path in json_files:
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                guild_id = os.path.basename(file_path).replace('.json', '')
                info = data.get("info", {})
                name = info.get("name", f"Server {guild_id}")
                
                # Генерируем slug
                slug = generate_server_slug(name, guild_id)
                server_slug_cache[slug] = guild_id
                
                servers_data[guild_id] = data
            print(f"Загружен сервер: {name} → /servers/{slug}")
        except Exception as e:
            print(f"Ошибка загрузки {file_path}: {e}")

# Загружаем данные при старте
load_servers_data()

@app.route("/server/<slug>")
def server_detail(slug):
    guild_id = None
    
    # 1. Сначала ищем по slug в кэше (название → ID)
    if slug in server_slug_cache:
        guild_id = server_slug_cache[slug]
    
    # 2. Если не нашли — проверяем, является ли slug чистым ID
    elif slug.isdigit() and slug in servers_data:
        guild_id = slug
    
    # 3. Если ничего не нашли — 404
    if not guild_id or guild_id not in servers_data:
        abort(404)
    
    data = servers_data[guild_id]
    info = data.get("info", {})
    
    return render_template(
        "server_detail.html",
        server=data,
        info=info,
        guild_id=guild_id
    )

@app.route("/guides")
def guides():
    guides_json_path = os.path. join(DATA_PAGES_DIR, 'guides.json')
    guides_list = []
    
    if os.path.exists(guides_json_path):
        try:
            with open(guides_json_path, 'r', encoding='utf-8') as f:
                raw_guides = json.load(f)
            
            for guide in raw_guides:
                title = guide.get('title', 'Без названия')
                source = guide.get('source', '')
                guide_type = guide.get('type', 'image')  # image или youtube
                
                if guide_type == 'youtube':
                    # Извлекаем video_id из ссылки YouTube
                    match = re.search(r'(?:v=|\/)([0-9A-Za-z_-]{11})', source)
                    if match:
                        video_id = match.group(1)
                        preview_url = f"https://img.youtube.com/vi/{video_id}/hqdefault.jpg"
                        link = source
                    else:
                        preview_url = None
                        link = '#'
                else:  # image
                    preview_url = url_for('static', filename=f'img/guides/{source}')
                    link = preview_url  # Клик открывает изображение
                
                if preview_url:
                    guides_list.append({
                        'title': title,
                        'preview_url': preview_url,
                        'link': link
                    })
        except Exception as e:
            print(f"Ошибка загрузки guides.json: {e}")
    
    return render_template(
        "guides.html",
        guides=guides_list,
        total_guides=len(guides_list)
    )

@app.route("/materials")
def materials():
    materials_json_path = os.path. join(DATA_PAGES_DIR, 'materials.json')
    materials_list = []
    all_tags = set()
    
    if os.path.exists(materials_json_path):
        try:
            with open(materials_json_path, 'r', encoding='utf-8') as f:
                raw_materials = json.load(f)
            
            for mat in raw_materials:
                title = mat.get('title', 'Без названия')
                image = mat.get('image', '')
                tag = mat.get('tag', 'Без категории')  # Теперь один тег — поле "tag"
                
                all_tags.add(tag)
                
                preview_url = url_for('static', filename=f'img/materials/{image}') if image else None
                
                if preview_url:
                    materials_list.append({
                        'title': title,
                        'preview_url': preview_url,
                        'tag': tag
                    })
        except Exception as e:
            print(f"Ошибка загрузки materials.json: {e}")
    
    # Добавляем "Все" в начало
    sorted_tags = ['Все'] + sorted(all_tags - {'Все'})
    
    return render_template(
        "materials.html",
        materials=materials_list,
        tags=sorted_tags,
        total_materials=len(materials_list)
    )

@app.route("/info")
def info():
    return render_template("info.html")

# ============= АДМИН-ПАНЕЛЬ В SITE.PY =============

# Конфигурация
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD")
ADMIN_SESSIONS = {}
SESSION_TIMEOUT = 3600  # 1 час

# ============= ХЕЛПЕР ФУНКЦИИ =============

def check_admin_auth():
    """Проверяет авторизацию админа"""
    if 'admin_token' not in session:
        return False
    token = session. get('admin_token')
    if token not in ADMIN_SESSIONS: 
        return False
    if time. time() > ADMIN_SESSIONS[token]: 
        del ADMIN_SESSIONS[token]
        session.pop('admin_token', None)
        return False
    return True

def load_admin_json(filename):
    """Загружает JSON для админ-панели"""
    filepath = os.path.join(DATA_PAGES_DIR, filename)
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            return json.load(f)
    except:
        return []

def save_admin_json(filename, data):
    """Сохраняет JSON из админ-панели"""
    filepath = os.path.join(DATA_PAGES_DIR, filename)
    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=4)

def process_form_data(params, filename):
    """Обрабатывает данные формы админ-панели"""
    new_item = {
        "id": params.get("id", [""])[0],
        "name": params.get("name", [""])[0] or params.get("id", [""])[0],
        "description": params.get("description", [""])[0].replace("\r\n", "\n"),
    }

    if "organizations" in filename:
        new_item. update({
            "created":  params.get("created", [""])[0],
            "closed": params.get("closed", [""])[0] or None,
            "reason_for_closing": params.get("reason_for_closing", [""])[0] or None,
            "peak_members": params.get("peak_members", [""])[0],
            "leader":  [x.strip() for x in params.get("leader", [""])[0].split('\n') if x.strip()],
        })
    elif "personalities" in filename:
        new_item.update({
            "created": params.get("created", [""])[0],
            "departed": params.get("departed", [""])[0] or None,
            "old_nicknames": params.get("old_nicknames", [""])[0],
        })
    elif "events" in filename:
        new_item.update({
            "event_type": params.get("event_type", [""])[0],
            "date": params.get("date", [""])[0],
        })

    return new_item

# ============= РОУТЫ =============

@app.route('/admin/login', methods=['GET', 'POST'])
def admin_login():
    """Страница входа в админ-панель"""
    if request.method == 'POST': 
        password = request.form.get('password', '')
        if password == ADMIN_PASSWORD:
            token = secrets.token_hex(16)
            ADMIN_SESSIONS[token] = time. time() + SESSION_TIMEOUT
            session['admin_token'] = token
            flash('Вы успешно авторизованы', 'success')
            return redirect(url_for('admin_panel'))
        else:
            flash('Неверный пароль', 'error')
    
    return render_template('admin_login.html')

@app.route('/admin')
def admin_panel():
    """Главная админ-панель"""
    if not check_admin_auth():
        return redirect(url_for('admin_login'))
    
    return render_template('admin_panel.html')

@app.route('/admin/logout')
def admin_logout():
    """Выход из админ-панели"""
    token = session.get('admin_token')
    if token in ADMIN_SESSIONS:
        del ADMIN_SESSIONS[token]
    session.pop('admin_token', None)
    flash('Вы вышли из админ-панели', 'success')
    return redirect(url_for('admin_login'))

@app.route('/admin/edit/<path:filename>', methods=['GET', 'POST'])
def admin_edit(filename):
    if not check_admin_auth():
        return redirect(url_for('admin_login'))

    # Определяем где хранится файл
    if filename.startswith(('materials/', 'guides/')):
        filepath = os.path.join(app.root_path, 'static', 'img', filename)
    else:
        filepath = os.path.join(DATA_PAGES_DIR, filename)

    if not os.path.exists(filepath):
        abort(404)

    # Загружаем данные
    with open(filepath, 'r', encoding='utf-8') as f:
        try:
            data = json.load(f)
        except json.JSONDecodeError:
            data = []

    # Индекс редактируемой записи
    idx = request.args.get("id", type=int, default=None)
    if idx is not None and 0 <= idx < len(data):
        item = data[idx]
    else:
        item = {}
        idx = -1

    if request.method == 'POST':
        form_data = request.form.to_dict(flat=False)
        
        # Разные типы данных
        if filename.endswith('.json') and not filename.startswith(('materials/', 'guides/')):
            new_item = process_form_data(form_data, filename)
        else:
            # Для материалов и гайдов
            new_item = {
                "title": form_data.get("title", [""])[0],
                "preview_url": form_data.get("preview_url", [""])[0],
            }
            if filename.startswith('materials/'):
                new_item["tag"] = form_data.get("tag", [""])[0]
                new_item["description"] = form_data.get("description", [""])[0]

        form_idx = int(request.form.get("index", -1))
        if form_idx == -1:
            data.append(new_item)
            idx = len(data) - 1
        else:
            data[form_idx] = new_item
            idx = form_idx

        # Сохраняем
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=4)

        flash("Запись успешно сохранена", "success")
        return redirect(url_for('admin_edit', filename=filename, id=idx))

    return render_template('admin_editor.html', data=data, item=item, idx=idx, filename=filename, enumerate=enumerate)



@app.route('/admin/delete/<filename>', methods=['POST'])
def admin_delete(filename):
    """Удаление записи"""
    if not check_admin_auth():
        abort(403)
    
    # Безопасность
    if not filename.endswith('. json') or '/' in filename or '\\' in filename:
        abort(400)
    
    filepath = os.path.join(DATA_PAGES_DIR, filename)
    if not os.path.exists(filepath):
        abort(404)
    
    data = load_admin_json(filename)
    idx = int(request.form.get('index', -1))
    
    if 0 <= idx < len(data):
        deleted_item = data.pop(idx)
        save_admin_json(filename, data)
        
        # Обновляем глобальные переменные
        global organizations_data, personalities_data, events_data
        if "organizations" in filename:
            organizations_data = data
        elif "personalities" in filename:
            personalities_data = data
        elif "events" in filename:
            events_data = data
        
        flash(f'Запись "{deleted_item. get("name") or deleted_item.get("id")}" успешно удалена', 'success')
    
    return redirect(url_for('admin_editor', filename=filename))

@app.route('/admin_static/<path:filename>')
def admin_static_files(filename):
    """Отдача статических файлов админ-панели"""
    admin_static_dir = os.path.join(os.path.dirname(__file__), 'admin_static')
    return send_from_directory(admin_static_dir, filename)

if __name__ == '__main__':
    print("🌐 Запускаю Flask-сайт на http://0.0.0.0:5000")
    app.run(host='0.0.0.0', port=5000, debug=True, use_reloader=False)