#!/bin/bash
LOG_DIR="/var/log/ppamappcaba.pythonanywhere.com"

echo "Limpiando logs en $LOG_DIR..."

# Truncar archivo error.log
: > "$LOG_DIR/ppamappcaba.pythonanywhere.com.error.log"

# Truncar archivo server.log
: > "$LOG_DIR/ppamappcaba.pythonanywhere.com.server.log"

echo "Logs limpiados correctamente."
