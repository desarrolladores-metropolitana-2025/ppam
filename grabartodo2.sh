#!/bin/bash

# Colores
VERDE="\e[32m"
ROJO="\e[31m"
AMARILLO="\e[33m"
RESET="\e[0m"

echo -e "${VERDE}==========================================${RESET}"
echo -e "${VERDE}   SISTEMA PPAM - Equipo desarrolladores  ${RESET}"
echo -e "${VERDE}   Guardando Todo y Sincronizando Ramas   ${RESET}"
echo -e "${VERDE}==========================================${RESET}"
echo

# Función para abortar el script si falla un comando
check_error() {
    if [ $? -ne 0 ]; then
        echo -e "${ROJO}❌ Error en el último comando. Abortando.${RESET}"
        git checkout main 2>/dev/null
        exit 1
    fi
}

echo -e "${AMARILLO}→ Cambiando a rama MAIN${RESET}"
git checkout main
check_error

echo -e "${AMARILLO}→ Agregando cambios locales...${RESET}"
git add .

# Si no hay cambios, evitar commit vacío
if git diff --cached --quiet; then
    echo -e "${AMARILLO}⚠ No hay cambios para commitear.${RESET}"
else
    echo -e "${AMARILLO}→ Haciendo commit...${RESET}"
    git commit -m "Correcciones"
    check_error
fi

echo -e "${AMARILLO}→ Haciendo push a MAIN...${RESET}"
git push origin main
check_error

echo -e "${AMARILLO}→ Cambiando a desarrollo_PPAM...${RESET}"
git checkout desarrollo_PPAM
check_error

echo -e "${AMARILLO}→ Reseteando desarrollo_PPAM contra MAIN (hard reset)...${RESET}"
git reset --hard main
check_error

echo -e "${AMARILLO}→ Push forzado a desarrollo_PPAM...${RESET}"
git push -f origin desarrollo_PPAM
check_error

echo -e "${AMARILLO}→ Volviendo a MAIN${RESET}"
git checkout main
check_error

echo
echo -e "${VERDE}✔ Proceso completado sin errores${RESET}"
echo

read -p "Presione Enter para salir..."





