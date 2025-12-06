#!/usr/bin/env bash
# tools.sh - interactive bash menu (arrow keys + Enter)
# Style: professional blue highlight
# Requires: tput, curl, tar, grep, find, truncate, free, ps
set -o allexport
source /home/ppamappcaba/mysite/var.env
set +o allexport

USER="${PA_USERNAME}"
TOKEN="${PA_API_TOKEN}"
BASE="https://www.pythonanywhere.com/api/v0/user/${USER}"

if [ -z "$USER" ] || [ -z "$TOKEN" ]; then
  echo "Setear variables PA_USERNAME y PA_API_TOKEN en el entorno antes de ejecutar."
  exit 1
fi

# terminal control
ESC=$(printf "\033")
SAVE_CURSOR() { tput sc; }
RESTORE_CURSOR() { tput rc; }
CLEAR_LINE() { tput el; }

# draw menu with highlight index
menu_items=(
  "Listar webapps"
  "Reiniciar webapp"
  "Listar Scheduled Tasks"
  "Listar Workers"
  "Limpiar logs (>1MB)"
  "Backup ~/mysite"
  "Uso CPU/RAM"
  "Buscar texto en ~/mysite"
  "API GET manual"
  "Salir"
)

draw_menu() {
  local sel=$1
  clear
  echo ""
  echo "=============================="
  echo "   PythonAnywhere Tools - PRO "
  echo "=============================="
  echo "  Use ↑ ↓  Enter (Esc para salir)"
  echo ""
  for i in "${!menu_items[@]}"; do
    local idx=$i
    local item="${menu_items[$i]}"
    if [ "$idx" -eq "$sel" ]; then
      # white on blue
      tput setab 4; tput setaf 7
      printf " > %s\n" "$item"
      tput sgr0
    else
      printf "   %s\n" "$item"
    fi
  done
}

api_get() {
  curl -s -H "Authorization: Token $TOKEN" "$BASE/$1"
}

api_post() {
  curl -s -X POST -H "Authorization: Token $TOKEN" -H "Content-Type: application/json" -d "$2" "$BASE/$1"
}

limpiar_logs() {
  local root=~/logs
  local count=0
  if [ -d "$root" ]; then
    while IFS= read -r -d '' f; do
      if [ "$(stat -c%s "$f")" -gt 1000000 ]; then
        : > "$f"
        count=$((count+1))
      fi
    done < <(find "$root" -type f -print0)
  fi
  echo "Truncated $count files in $root"
  read -p "Presiona Enter..."
}

backup_mysite() {
  local target="/home/${USER}/mysite"
  if [ ! -d "$target" ]; then
    echo "No se encontró $target"
    read -p "Presiona Enter..."
    return
  fi
  local out="/home/${USER}/backup_$(date +%F).tar.gz"
  tar -czf "$out" "$target"
  echo "Backup creado: $out"
  read -p "Presiona Enter..."
}

buscar_texto() {
  read -p "Texto a buscar: " q
  if [ -z "$q" ]; then return; fi
  echo "Buscando..."
  grep -Rni --exclude-dir=.git "$q" ~/mysite || true
  read -p "Presiona Enter..."
}

uso_sistema() {
  echo "CPU - procesos top:"
  ps -eo pid,cmd,%cpu --sort=-%cpu | head -n 10
  echo ""
  echo "RAM:"
  free -h
  read -p "Presiona Enter..."
}

# read arrow keys
read_key() {
  IFS= read -rsn1 key 2>/dev/null
  if [[ $key == $ESC ]]; then
    IFS= read -rsn2 -t 0.1 key2 2>/dev/null
    key+="$key2"
  fi
  echo "$key"
}

# main loop
selected=0
while true; do
  draw_menu "$selected"
  key=$(read_key)
  case "$key" in
    $ESC'[A'|k) # up
      selected=$(( (selected - 1 + ${#menu_items[@]}) % ${#menu_items[@]} ))
      ;;
    $ESC'[B'|j) # down
      selected=$(( (selected + 1) % ${#menu_items[@]} ))
      ;;
    ""|$'\n' ) # Enter
      choice="${menu_items[$selected]}"
      case "$choice" in
        "Listar webapps")
          api_get "webapps/" | sed 's/\\n/\n/g' | less -R
          ;;
        "Reiniciar webapp")
          read -p "Nombre interno de webapp: " w
          api_post "webapps/${w}/reload/" "{}" | sed 's/\\n/\n/g'
          read -p "Presiona Enter..."
          ;;
        "Listar Scheduled Tasks")
          api_get "scheduled_tasks/" | less -R
          ;;
        "Listar Workers")
          api_get "workers/" | less -R
          ;;
        "Limpiar logs (>1MB)")
          limpiar_logs
          ;;
        "Backup ~/mysite")
          backup_mysite
          ;;
        "Uso CPU/RAM")
          uso_sistema
          ;;
        "Buscar texto en ~/mysite")
          buscar_texto
          ;;
        "API GET manual")
          read -p "Endpoint (ej: consoles/): " ep
          api_get "$ep" | less -R
          ;;
        "Salir")
          clear
          exit 0
          ;;
      esac
      ;;
    $ESC) # single ESC pressed
      clear; exit 0
      ;;
    *) ;;
  esac
done
