#!/usr/bin/env python3
import os

LOG_DIR = "/var/log/ppamappcaba.pythonanywhere.com"

FILES = [
    "ppamappcaba.pythonanywhere.com.error.log",
    "ppamappcaba.pythonanywhere.com.server.log",
]

for f in FILES:
    path = os.path.join(LOG_DIR, f)
    if os.path.exists(path):
        print(f"Limpiando {path}...")
        with open(path, "w") as log:
            log.truncate(0)

print("Logs limpiados.")
