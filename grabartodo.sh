#!/bin/bash

###############################################
#        PPAM - Sistema de Desarrollo
###############################################

# ===== Colores =====
RED="\e[31m"
GREEN="\e[32m"
YELLOW="\e[33m"
BLUE="\e[34m"
CYAN="\e[36m"
MAGENTA="\e[35m"
RESET="\e[0m"

# ===== Banner =====
clear
echo -e "${RED}"
echo "┌──────────────────────────────────────────────────────────┐"
echo "│                                                          │"
echo "│      🌐  Sistema PPAM – Equipo de Desarrolladores        │"
echo "│                                                          │"
echo "└──────────────────────────────────────────────────────────┘"
echo -e "${RESET}"

# ===== Configuración =====
FECHA=$(date +"%Y-%m-%d %H:%M:%S")
LOG_DIR="./ppamtools_data"
LOGFILE="$LOG_DIR/grabartodo_log.txt"

# Crear carpeta de logs si no existe
mkdir -p "$LOG_DIR"

echo -e "${BLUE}===========================================================${RESET}"
echo -e "${BLUE}   🔄 Guardando, sincronizando y actualizando repos        ${RESET}"
echo -e "${BLUE}   📅 Ejecutado: $FECHA                                     ${RESET}"
echo -e "${BLUE}===========================================================${RESET}"
echo


# ===== Función de Log =====
log() {
    echo "[$(date +"%Y-%m-%d %H:%M:%S")] $1" >> "$LOGFILE"
}

# ===== Función de Chequeo de errores =====
check() {
    if [ $? -ne 0 ]; then
        echo -e "${RED}❌ Error: $1${RESET}"
        log "ERROR: $1"
        git checkout main 2>/dev/null
        echo -e "${YELLOW}⚠ Script detenido para evitar inconsistencias.${RESET}"
        exit 1
    fi
}

# ===== Chequeo de Internet =====
echo -e "${YELLOW}🌐 Verificando conexión a GitHub...${RESET}"
ping -c 1 github.com >/dev/null 2>&1
if [ $? -ne 0 ]; then
    echo -e "${RED}❌ Sin conexión. No se puede continuar.${RESET}"
    log "Sin conexión a Internet"
    exit 1
fi
echo -e "${GREEN}✔ Conexión OK${RESET}"
echo


###############################################
#                PROCESO MAIN
###############################################

echo -e "${CYAN}➡ Cambiando a rama MAIN${RESET}"
git checkout main
check "No se pudo cambiar a main."

echo -e "${CYAN}➡ Agregando cambios locales${RESET}"
git add .

if git diff --cached --quiet; then
    echo -e "${YELLOW}⚠ No hay cambios para commitear.${RESET}"
    log "No hubo cambios para commitear."
else
    MENSAJE="Correcciones automáticas – $FECHA"
    echo -e "${CYAN}📝 Commit: '$MENSAJE'${RESET}"
    git commit -m "$MENSAJE"
    check "Error en commit."
fi

echo -e "${CYAN}⬆ Subiendo cambios a MAIN...${RESET}"
git push origin main
check "Error en push a main."
log "Push main OK"


###############################################
#            PROCESO DESARROLLO_PPAM
###############################################

echo -e "${MAGENTA}➡ Cambiando a rama desarrollo_PPAM${RESET}"
git checkout desarrollo_PPAM
check "No se pudo cambiar a desarrollo_PPAM."

echo -e "${MAGENTA}🔧 Reseteando desarrollo_PPAM con main${RESET}"
git reset --hard main
check "No se pudo hacer reset hard."

echo -e "${MAGENTA}⬆ Push forzado a desarrollo_PPAM...${RESET}"
git push -f origin desarrollo_PPAM
check "Error push -f a desarrollo_PPAM."
log "Push -f desarrollo_PPAM OK"


###############################################
#                 FINALIZACIÓN
###############################################

git checkout main >/dev/null 2>&1

echo
echo -e "${GREEN}✔ Proceso completado sin errores${RESET}"
echo -e "${GREEN}📄 Log guardado en: ${LOGFILE}${RESET}"
log "Proceso completado OK"

echo
echo -e "${BLUE}===========================================================${RESET}"
echo -e "${BLUE}               Operación finalizada con éxito              ${RESET}"
echo -e "${BLUE}===========================================================${RESET}"
echo

read -p "Presione Enter para salir..."



