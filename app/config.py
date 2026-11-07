from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

ROOT_DIR = Path(__file__).resolve().parent.parent
load_dotenv(ROOT_DIR / ".env")

DB_PATH = Path(os.getenv("DB_PATH", str(ROOT_DIR / "media_pipeline.sqlite3")))
GENERATED_DIR = Path(os.getenv("GENERATED_DIR", str(ROOT_DIR / "generated")))
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434").rstrip("/")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "gemma4:26b").strip()
OLLAMA_TIMEOUT = int(os.getenv("OLLAMA_TIMEOUT", "600"))
OLLAMA_STAGE_KEEP_ALIVE = os.getenv("OLLAMA_STAGE_KEEP_ALIVE", "10m")
OLLAMA_NUM_CTX = int(os.getenv("OLLAMA_NUM_CTX", "8192"))
OLLAMA_UNLOAD_AFTER_GENERATION = os.getenv("OLLAMA_UNLOAD_AFTER_GENERATION", "true").strip().lower() in {"1", "true", "yes", "on"}
COMFYUI_BASE_URL = os.getenv("COMFYUI_BASE_URL", "http://127.0.0.1:8188").rstrip("/")
COMFYUI_TIMEOUT = int(os.getenv("COMFYUI_TIMEOUT", "900"))
COMFYUI_CHECKPOINT = os.getenv("COMFYUI_CHECKPOINT", "v1-5-pruned-emaonly.safetensors").strip()

# SD 1.5-friendly portrait comic preset. Keep these conservative for 12GB VRAM.
COMFYUI_WIDTH = int(os.getenv("COMFYUI_WIDTH", "512"))
COMFYUI_HEIGHT = int(os.getenv("COMFYUI_HEIGHT", "640"))
COMFYUI_STEPS = int(os.getenv("COMFYUI_STEPS", "28"))
COMFYUI_CFG = float(os.getenv("COMFYUI_CFG", "6.0"))
COMFYUI_SAMPLER = os.getenv("COMFYUI_SAMPLER", "dpmpp_2m").strip()
COMFYUI_SCHEDULER = os.getenv("COMFYUI_SCHEDULER", "karras").strip()
COMFYUI_HIRES_ENABLED = os.getenv("COMFYUI_HIRES_ENABLED", "true").strip().lower() in {"1", "true", "yes", "on"}
COMFYUI_HIRES_SCALE = float(os.getenv("COMFYUI_HIRES_SCALE", "1.5"))
COMFYUI_HIRES_METHOD = os.getenv("COMFYUI_HIRES_METHOD", "bislerp").strip()
COMFYUI_HIRES_STEPS = int(os.getenv("COMFYUI_HIRES_STEPS", "12"))
COMFYUI_HIRES_CFG = float(os.getenv("COMFYUI_HIRES_CFG", "5.5"))
COMFYUI_HIRES_DENOISE = float(os.getenv("COMFYUI_HIRES_DENOISE", "0.28"))
COMFYUI_SEED_MODE = os.getenv("COMFYUI_SEED_MODE", "shared").strip().lower()
