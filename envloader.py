#!/usr/bin/env python3
# envloader.py

import os

def load_env(env_file=None):
    """Carga variables desde un archivo .env"""
    env_file = env_file or "/home/ppamappcaba/mysite/var.env"

    if not os.path.exists(env_file):
        print(f"[envloader] No se encontró {env_file}")
        return

    with open(env_file) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" not in line:
                continue
            key, val = line.split("=", 1)
            os.environ[key] = val
    # Debug opcional:
    # print("[envloader] Variables cargadas:", list(os.environ.keys()))
