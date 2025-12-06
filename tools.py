#!/usr/bin/env python3
"""
tools.py - Interactive PythonAnywhere CLI (curses)
Style: Professional (blue highlight)
Requires: python3, requests, psutil (psutil optional; fallback if missing)
Env vars: PA_USERNAME, PA_TOKEN
"""
import os
import json
import shutil
import subprocess
import requests
import datetime
import textwrap
import curses
import envloader

# Carga automática de var.env
envloader.load_env()

USER = os.environ.get("PA_USERNAME")
TOKEN = os.environ.get("PA_API_TOKEN")
BASE = f"https://www.pythonanywhere.com/api/v0/user/{USER}/"

# ----- API helpers -----
def api_get(path):
    url = BASE + path.lstrip("/")
    try:
        r = requests.get(url, headers={"Authorization": f"Token {TOKEN}"}, timeout=12)
    except Exception as e:
        return {"error": str(e)}
    try:
        return r.json()
    except Exception:
        return {"status": r.status_code, "text": r.text[:4000]}

def api_post(path, json_body=None):
    url = BASE + path.lstrip("/")
    try:
        r = requests.post(url, headers={"Authorization": f"Token {TOKEN}"}, json=json_body, timeout=12)
    except Exception as e:
        return {"error": str(e)}
    try:
        return r.json()
    except Exception:
        return {"status": r.status_code, "text": r.text[:4000]}

# ----- Utilities -----
def limpiar_logs():
    root = os.path.expanduser("~/logs")
    count = 0
    for path, _, files in os.walk(root):
        for f in files:
            full = os.path.join(path, f)
            try:
                if os.path.getsize(full) > 1_000_000:
                    open(full, "w").close()
                    count += 1
            except Exception:
                continue
    return f"Truncated {count} log files in {root}"

def backup_mysite():
    target = os.path.expanduser(f"/home/{USER}/mysite")
    if not os.path.exists(target):
        return f"Source not found: {target}"
    name = f"/home/{USER}/backup_{datetime.date.today().isoformat()}"
    shutil.make_archive(name, "gztar", target)
    return f"Backup created: {name}.tar.gz"

def buscar_texto(query):
    root = os.path.expanduser("~/mysite")
    hits = []
    for path, _, files in os.walk(root):
        for f in files:
            full = os.path.join(path, f)
            try:
                with open(full, errors="ignore", encoding="utf-8") as fh:
                    txt = fh.read()
                if query.lower() in txt.lower():
                    hits.append(full)
            except Exception:
                continue
    return hits

def uso_sistema():
    try:
        import psutil
    except Exception:
        # fallback to basic tools
        out = subprocess.run(["uptime"], capture_output=True, text=True)
        mem = subprocess.run(["free", "-h"], capture_output=True, text=True)
        return {"uptime": out.stdout.strip(), "mem": mem.stdout.strip()}
    return {
        "cpu_percent": psutil.cpu_percent(interval=0.5),
        "virtual_memory": dict(psutil.virtual_memory()._asdict())
    }

# ----- UI (curses) -----
MENU = [
    "Listar webapps",
    "Reiniciar webapp",
    "Listar Scheduled Tasks",
    "Listar Workers",
    "Limpiar logs (>1MB)",
    "Backup ~/mysite",
    "Uso CPU/RAM",
    "Buscar texto en ~/mysite",
    "API GET manual",
    "Salir"
]

HELP = "Usá ↑ ↓ para navegar, ENTER para seleccionar. Esc para salir."

def draw_menu(stdscr, selected):
    stdscr.clear()
    h, w = stdscr.getmaxyx()
    title = "PythonAnywhere Tools — PRO"
    stdscr.attron(curses.A_BOLD)
    stdscr.addstr(1, max(0, (w//2 - len(title)//2)), title)
    stdscr.attroff(curses.A_BOLD)
    stdscr.addstr(3, 2, HELP)
    for i, item in enumerate(MENU):
        x = 4 + i
        if i == selected:
            # blue background style
            stdscr.attron(curses.color_pair(1))
            stdscr.addstr(x, 6, f"> {item}")
            stdscr.attroff(curses.color_pair(1))
        else:
            stdscr.addstr(x, 8, item)
    stdscr.refresh()

def prompt_input(stdscr, prompt):
    curses.echo()
    stdscr.addstr(curses.LINES-3, 2, " " * (curses.COLS-4))
    stdscr.addstr(curses.LINES-3, 2, prompt)
    stdscr.refresh()
    s = stdscr.getstr(curses.LINES-3, 2 + len(prompt)).decode(errors="ignore")
    curses.noecho()
    return s.strip()

def show_text(stdscr, title, text):
    stdscr.clear()
    h, w = stdscr.getmaxyx()
    stdscr.attron(curses.A_BOLD)
    stdscr.addstr(1, max(0, (w//2 - len(title)//2)), title)
    stdscr.attroff(curses.A_BOLD)
    lines = textwrap.wrap(text, w-4)
    y = 3
    for line in lines:
        if y < h-3:
            stdscr.addstr(y, 2, line)
            y += 1
        else:
            break
    stdscr.addstr(h-2, 2, "Presiona cualquier tecla para volver...")
    stdscr.refresh()
    stdscr.getch()

def main(stdscr):
    # colors: blue background with white text for highlight
    curses.start_color()
    curses.use_default_colors()
    curses.init_pair(1, curses.COLOR_WHITE, curses.COLOR_BLUE)

    selected = 0
    while True:
        draw_menu(stdscr, selected)
        k = stdscr.getch()
        if k in (curses.KEY_UP, ord('k')):
            selected = (selected - 1) % len(MENU)
        elif k in (curses.KEY_DOWN, ord('j')):
            selected = (selected + 1) % len(MENU)
        elif k in (curses.KEY_ENTER, 10, 13):
            choice = MENU[selected]
            if choice == "Listar webapps":
                data = api_get("webapps/")
                pretty = json.dumps(data, indent=2, ensure_ascii=False)
                show_text(stdscr, "Webapps", pretty)
            elif choice == "Reiniciar webapp":
                name = prompt_input(stdscr, "Nombre interno (ej: ppamappcaba): ")
                if name:
                    res = api_post(f"webapps/{name}/reload/")
                    show_text(stdscr, "Reload result", json.dumps(res, indent=2, ensure_ascii=False))
            elif choice == "Listar Scheduled Tasks":
                res = api_get("scheduled_tasks/")
                show_text(stdscr, "Scheduled Tasks", json.dumps(res, indent=2, ensure_ascii=False))
            elif choice == "Listar Workers":
                res = api_get("workers/")
                show_text(stdscr, "Workers", json.dumps(res, indent=2, ensure_ascii=False))
            elif choice == "Limpiar logs (>1MB)":
                out = limpiar_logs()
                show_text(stdscr, "Limpiar logs", out)
            elif choice == "Backup ~/mysite":
                out = backup_mysite()
                show_text(stdscr, "Backup", out)
            elif choice == "Uso CPU/RAM":
                out = uso_sistema()
                show_text(stdscr, "Uso sistema", json.dumps(out, indent=2, ensure_ascii=False))
            elif choice == "Buscar texto en ~/mysite":
                q = prompt_input(stdscr, "Texto a buscar: ")
                if q:
                    hits = buscar_texto(q)
                    if not hits:
                        show_text(stdscr, "Buscar", "No se encontraron coincidencias.")
                    else:
                        # show first 2000 chars of list
                        show_text(stdscr, "Buscar", "\n".join(hits))
            elif choice == "API GET manual":
                ep = prompt_input(stdscr, "Endpoint (ej: consoles/): ")
                if ep:
                    out = api_get(ep)
                    show_text(stdscr, f"GET {ep}", json.dumps(out, indent=2, ensure_ascii=False))
            elif choice == "Salir":
                break
        elif k in (27,):  # ESC
            break

if __name__ == "__main__":
    if not USER or not TOKEN:
        print("ERROR: configurá PA_USERNAME y PA_TOKEN en el entorno.")
        print("Ej: export PA_USERNAME=tuusuario; export PA_TOKEN=xxxx")
    else:
        curses.wrapper(main)
