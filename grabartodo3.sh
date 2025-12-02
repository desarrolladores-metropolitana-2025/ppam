#!/bin/bash
# ================================
#   Sistema PPAM - Repositorio
# ================================
ROJO="\e[31m"
RESET="\e[0m"
echo -e "${ROJO}_________________________________________________${RESET}"
echo -e "${ROJO}                                                 ${RESET}"
echo -e "${ROJO}     Sistema PPAM - equipo de desarrolladores    ${RESET}"
echo -e "${ROJO}_________________________________________________${RESET}"
#
# ================================
#   CONFIG & COLORES
# ================================
VERDE="\e[32m"
ROJO="\e[31m"
AMARILLO="\e[33m"
AZUL="\e[34m"
RESET="\e[0m"
# Carpeta donde guardar el log
LOG_DIR="./ppamtools_data"
LOGFILE="$LOG_DIR/grabartodo_log.txt"
FECHA=$(date +"%Y-%m-%d %H:%M:%S")
# LOGFILE="grabartodo_log.txt"

echo -e "${AZUL}=========================================${RESET}"
echo -e "${AZUL}    Guardando todo y sincronizando       ${RESET}"
echo -e "${AZUL}    Ejecutado: $FECHA                    ${RESET}"
echo -e "${AZUL}=========================================${RESET}"
echo

# ================================
#  Función de LOG
# ================================
log() {
    echo "[$(date +"%Y-%m-%d %H:%M:%S")] $1" >> "$LOGFILE"
}

# ================================
#  Función de chequeo de errores
# ================================
check() {
    if [ $? -ne 0 ]; then
        echo -e "${ROJO}❌ Error: $1${RESET}"
        log "ERROR: $1"
        git checkout main 2>/dev/null
        exit 1
    fi
}

# ================================
#  Chequeo de conexión a Internet
# ================================
echo -e "${AMARILLO}→ Verificando conexión a Internet...${RESET}"
ping -c 1 github.com >/dev/null 2>&1
if [ $? -ne 0 ]; then
    echo -e "${ROJO}❌ Sin conexión a GitHub. Abortando.${RESET}"
    exit 1
fi

echo -e "${VERDE}✔ Conexión OK${RESET}"
echo

# ================================
#   PROCESO MAIN
# ================================

echo -e "${AMARILLO}→ Cambiando a main${RESET}"
git checkout main
check "No se pudo cambiar a main."

echo -e "${AMARILLO}→ Agregando cambios...${RESET}"
git add .

# Si no hay cambios, se evita commit vacío
if git diff --cached --quiet; then
    echo -e "${AMARILLO}⚠ No hay cambios para commitear.${RESET}"
    log "No hubo cambios para commitear."
else
    MENSAJE="Correcciones $FECHA"
    echo -e "${AMARILLO}→ Commit: '$MENSAJE'${RESET}"
    git commit -m "$MENSAJE"
    check "Error en commit."
fi

echo -e "${AMARILLO}→ Push a main...${RESET}"
git push origin main
check "Error haciendo push a main."
log "Push main OK"

# ================================
#   PROCESO desarrollo_PPAM
# ================================
echo -e "${AMARILLO}→ Cambiando a desarrollo_PPAM${RESET}"
git checkout desarrollo_PPAM
check "No se pudo cambiar a desarrollo_PPAM."

echo -e "${AMARILLO}→ Reseteando con main${RESET}"
git reset --hard main
check "No se pudo hacer reset hard."

echo -e "${AMARILLO}→ Push forzado...${RESET}"
git push -f origin desarrollo_PPAM
check "Error push -f a desarrollo_PPAM."
log "Push -f desarrollo_PPAM OK"

# ================================
#   Finalizar
# ================================
git checkout main >/dev/null 2>&1

echo
echo -e "${VERDE}✔ Proceso completado sin errores${RESET}"
log "Proceso completado OK"

echo
read -p "Presione Enter para salir..."


