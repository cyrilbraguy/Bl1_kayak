"""live_search.py : lance pipeline.py en arrière-plan depuis le dashboard."""
from __future__ import annotations

import os
import subprocess
import sys
import threading
import time
from pathlib import Path

import availability as av

SRC_DIR = Path(__file__).resolve().parent
LOG_DIR = Path(os.getenv("LIVE_LOG_DIR", SRC_DIR.parent / "data" / "logs"))
LIVE_MAX_CITIES = int(os.getenv("LIVE_MAX_CITIES", "10"))
TIMEOUT_S = int(os.getenv("PIPELINE_TIMEOUT_MIN", "120")) * 60

LIVE_TOP_CITIES = int(os.getenv("LIVE_TOP_CITIES", "5"))
LIVE_MAX_RESULTS = int(os.getenv("LIVE_MAX_RESULTS", "6"))


EXIT_MESSAGES = {
    1: "La recherche a échoué (voir le journal ci-dessous).",
    2: "Aucun hôtel trouvé pour ces dates.",
    3: "Cette combinaison est déjà en base.",
    4: "Un autre pipeline est en cours, réessaie dans quelques minutes.",
}

# Un module n'est chargé qu'une fois par processus : ces dictionnaires sont partagés
# entre toutes les sessions Streamlit.
_PROCS: dict[av.SearchKey, subprocess.Popen] = {}
_STARTED: dict[av.SearchKey, float] = {}
_LOCK = threading.Lock()


class SearchBusy(RuntimeError):
    """Une recherche en direct est déjà en cours."""


def _log_path(key: av.SearchKey) -> Path:
    return LOG_DIR / f"live_{key.checkin:%Y%m%d}_{key.checkout:%Y%m%d}.log"


def start_search(key: av.SearchKey, max_price: float, top_n: int = LIVE_TOP_CITIES,
                 max_results: int = LIVE_MAX_RESULTS, force: bool = False) -> None:
    """Lance pipeline.py en arrière-plan avec les paramètres de l'interface."""
    if not max_price or max_price <= 0:
        raise ValueError("Le prix maximal doit être strictement positif.")
    with _LOCK:
        if any(p.poll() is None for p in _PROCS.values()):
            raise SearchBusy("Une recherche est déjà en cours, réessaie dans quelques minutes.")
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        cmd = [
            sys.executable, "pipeline.py",
            "--checkin", key.checkin.isoformat(), "--checkout", key.checkout.isoformat(),
            "--adults", str(key.n_adults), "--children", str(key.n_children),
            "--rooms", str(key.n_rooms),
            "--max-price", f"{float(max_price):g}",
            "--max-results", str(max_results), "--top-cities", str(top_n),
        ]
        if force:
            cmd.append("--force")
        with open(_log_path(key), "w", encoding="utf-8") as log:
            _PROCS[key] = subprocess.Popen(cmd, cwd=SRC_DIR, stdout=log, stderr=subprocess.STDOUT)
        _STARTED[key] = time.monotonic()


def search_status(key: av.SearchKey) -> tuple[str, int | None]:
    """("none" | "running" | "done" | "failed", code de sortie)."""
    p = _PROCS.get(key)
    if p is None:
        return "none", None
    rc = p.poll()
    if rc is None:
        if time.monotonic() - _STARTED.get(key, 0) > TIMEOUT_S:   # processus bloqué
            p.kill()
            av.PIPELINE_LOCK_PATH.unlink(missing_ok=True)
            return "failed", 1
        return "running", None
    return ("done" if rc == 0 else "failed"), rc


def log_tail(key: av.SearchKey, n: int = 12) -> str:
    try:
        lines = _log_path(key).read_text(encoding="utf-8", errors="replace").splitlines()
        return "\n".join(lines[-n:])
    except OSError:
        return ""


# updated version 

