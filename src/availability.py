"""
availability.py
===============
Gestion des « fenêtres de dates » déjà recherchées (en base) vs à rechercher (scraping lent).

Aucune dépendance Streamlit : utilisable dans pipeline.py ET dashboard_app.py.

Une recherche est identifiée par (checkin, checkout, n_adults, n_children, n_rooms),
car prix et disponibilités dépendent aussi de l'occupation.
"""
from __future__ import annotations

import logging
from datetime import date, datetime
from typing import Callable, Iterable, NamedTuple

import pandas as pd

logger = logging.getLogger(__name__)

# Interrupteur : False = dashboard en lecture seule sur le précalculé (mode actuel).
# Passer à True quand la recherche à la demande sera implémentée.
ENABLE_LIVE_SEARCH = False

# Occupation utilisée par le pipeline ET par défaut dans le dashboard.
# Elle doit être identique des deux côtés, sinon tout apparaît en « nouvelle recherche ».
DEFAULT_OCCUPANCY = {"n_adults": 2, "n_children": 0, "n_rooms": 1}

# Colonnes à ajouter à la table `hotels` (+ scraped_at pour la fraîcheur)
SEARCH_COLS = ["checkin_date", "checkout_date", "n_adults", "n_children", "n_rooms"]

EMOJI_IN_DB = "🟢"
EMOJI_NEW = "🟠"


class SearchKey(NamedTuple):
    checkin: date
    checkout: date
    n_adults: int
    n_children: int
    n_rooms: int


# ----------------------------------------------------------------------
# Utilitaires de base
# ----------------------------------------------------------------------
def to_date(value) -> date:
    """Normalise str / datetime / pd.Timestamp / np.datetime64 / date en datetime.date."""
    if isinstance(value, datetime):  # inclut pd.Timestamp (datetime est testé avant date)
        return value.date()
    if isinstance(value, date):
        return value
    return pd.to_datetime(value).date()


def make_key(
    checkin,
    checkout,
    n_adults: int = DEFAULT_OCCUPANCY["n_adults"],
    n_children: int = DEFAULT_OCCUPANCY["n_children"],
    n_rooms: int = DEFAULT_OCCUPANCY["n_rooms"],
) -> SearchKey:
    return SearchKey(to_date(checkin), to_date(checkout), int(n_adults), int(n_children), int(n_rooms))


def build_date_windows(date_span: Iterable, n_checkins: int = 4) -> list[tuple[date, date]]:
    """Fenêtres précalculées : j→j+4, j+1→j+4, j+2→j+4, j+3→j+4.

    Le checkout est la 5e date de prévision (ou la dernière disponible s'il y en a moins).
    """
    dates = sorted({to_date(d) for d in date_span})
    if len(dates) < 2:
        raise ValueError("Il faut au moins 2 dates de prévision pour construire une fenêtre")
    checkout = dates[min(4, len(dates) - 1)]
    return [(ci, checkout) for ci in dates[:n_checkins] if ci < checkout]


# ----------------------------------------------------------------------
# Statut « en base » / « nouvelle recherche »
# ----------------------------------------------------------------------
def keys_from_df(df: pd.DataFrame) -> set[SearchKey]:
    """Ensemble des recherches présentes dans un DataFrame (table hotels ou son DISTINCT)."""
    missing = [c for c in SEARCH_COLS if c not in df.columns]
    if missing:
        logger.warning("Colonnes absentes %s : aucune recherche précalculée reconnue", missing)
        return set()

    sub = df[SEARCH_COLS].dropna().drop_duplicates()  # anciennes lignes sans occupation ignorées
    return {
        make_key(r.checkin_date, r.checkout_date, r.n_adults, r.n_children, r.n_rooms)
        for r in sub.itertuples(index=False)
    }


def is_in_db(key: SearchKey, keys: set[SearchKey]) -> bool:
    return key in keys


def status_emoji(key: SearchKey, keys: set[SearchKey]) -> str:
    return EMOJI_IN_DB if is_in_db(key, keys) else EMOJI_NEW


def label(d: date, key: SearchKey, keys: set[SearchKey], fmt: str = "%d/%m") -> str:
    """Libellé d'une option de selectbox, ex. '🟢 24/09'."""
    return f"{status_emoji(key, keys)} {d.strftime(fmt)}"


def availability_matrix(
    dates: Iterable, occupancy: dict, keys: set[SearchKey], fmt: str = "%d/%m"
) -> pd.DataFrame:
    """Matrice lignes = check-in, colonnes = check-out, cellule = 🟢 / 🟠 (vide si invalide)."""
    ds = sorted({to_date(d) for d in dates})
    data = {
        co.strftime(fmt): [
            status_emoji(make_key(ci, co, **occupancy), keys) if ci < co else ""
            for ci in ds
        ]
        for co in ds
    }
    return pd.DataFrame(data, index=[ci.strftime(fmt) for ci in ds])


def estimate_search_minutes(n_cities: int, seconds_per_city: float = 30.0) -> float:
    """Durée estimée d'une recherche live. `seconds_per_city` est un PLACEHOLDER :
    mesure la vraie durée de collect_cities_hotels et remplace cette valeur."""
    return max(0.0, n_cities * seconds_per_city / 60.0)


# ----------------------------------------------------------------------
# Côté pipeline : lancer plusieurs recherches sans refaire celles déjà en base
# ----------------------------------------------------------------------
def run_hotel_searches(
    top_cities: pd.DataFrame,
    windows: list[tuple[date, date]],
    occupancy: dict,
    collect_fn: Callable,
    select_fn: Callable,
    *,
    skip_keys: set[SearchKey] | None = None,
    max_results: int = 5,
    max_price: float = 500,
    top_n: int = 20,
) -> tuple[pd.DataFrame, list[SearchKey]]:
    """Exécute une recherche par fenêtre de dates et concatène les résultats.

    collect_fn = collect_cities_hotels, select_fn = select_top_hotels (injectés : testable seul).
    Une fenêtre en échec ne bloque pas les suivantes ; elle est renvoyée dans `failed`.
    Une recherche qui ne renvoie aucun hôtel ne laisse aucune ligne : elle sera retentée au run suivant.
    """
    skip_keys = skip_keys or set()
    frames: list[pd.DataFrame] = []
    failed: list[SearchKey] = []

    for checkin, checkout in windows:
        key = make_key(checkin, checkout, **occupancy)
        if key in skip_keys:
            logger.info("Déjà en base, ignorée : %s", key)
            continue
        try:
            raw = collect_fn(
                top_cities, checkin.isoformat(), checkout.isoformat(),
                key.n_adults, key.n_children, key.n_rooms, max_results,
            )
            top = select_fn(raw, n=top_n, criterion="combined", max_price=max_price, out_all=True)
        except Exception:
            logger.exception("Échec de la recherche %s", key)
            failed.append(key)
            continue

        if top is None or top.empty:
            logger.warning("Aucun hôtel pour %s", key)
            continue

        top = top.copy()
        top["checkin_date"] = key.checkin
        top["checkout_date"] = key.checkout
        top["n_adults"] = key.n_adults
        top["n_children"] = key.n_children
        top["n_rooms"] = key.n_rooms
        top["scraped_at"] = pd.Timestamp.now()
        frames.append(top)
        logger.info("Recherche terminée %s : %d hôtels", key, len(top))

    result = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
    return result, failed
