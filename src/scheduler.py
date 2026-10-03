"""scheduler.py : lance pipeline.py à heures fixes (bibliothèque standard uniquement)."""
from __future__ import annotations

import logging
import os
import subprocess
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

logging.basicConfig(level=logging.INFO, format="%(asctime)s [scheduler] %(message)s")
log = logging.getLogger("scheduler")

TZ = ZoneInfo(os.getenv("TZ", "Europe/Paris"))
HOURS = sorted({int(h) for h in os.getenv("PIPELINE_HOURS", "6,18").split(",") if h.strip()})
TIMEOUT_S = int(os.getenv("PIPELINE_TIMEOUT_MIN", "120")) * 60
RUN_ON_START = os.getenv("PIPELINE_RUN_ON_START", "0") == "1"
SRC_DIR = Path(__file__).resolve().parent


def next_run(now: datetime) -> datetime:
    """Prochaine heure de lancement strictement après `now`."""
    candidats = [now.replace(hour=h, minute=0, second=0, microsecond=0) for h in HOURS]
    futurs = [c for c in candidats if c > now]
    return futurs[0] if futurs else candidats[0] + timedelta(days=1)


def run_pipeline() -> None:
    """Exécute pipeline.py ; un échec est journalisé mais n'arrête jamais l'ordonnanceur."""
    log.info("Lancement de pipeline.py")
    debut = time.monotonic()
    try:
        res = subprocess.run([sys.executable, "pipeline.py"], cwd=SRC_DIR,
                             timeout=TIMEOUT_S, check=False)
        log.info("Pipeline terminé (code %s) en %.1f min", res.returncode,
                 (time.monotonic() - debut) / 60)
    except subprocess.TimeoutExpired:
        log.error("Pipeline interrompu : dépassement de %d min", TIMEOUT_S // 60)
    except Exception:
        log.exception("Erreur inattendue au lancement du pipeline")


def main() -> None:
    if not HOURS or any(not 0 <= h <= 23 for h in HOURS):
        raise SystemExit(f"PIPELINE_HOURS invalide : {HOURS}")
    log.info("Heures de lancement : %s (fuseau %s)", HOURS, TZ)
    if RUN_ON_START:
        run_pipeline()
    while True:
        cible = next_run(datetime.now(TZ))
        log.info("Prochain run : %s", cible.isoformat(timespec="minutes"))
        while (reste := (cible - datetime.now(TZ)).total_seconds()) > 0:
            time.sleep(min(60, reste))  # petits pas : robuste aux changements d'heure
        run_pipeline()


if __name__ == "__main__":
    main()