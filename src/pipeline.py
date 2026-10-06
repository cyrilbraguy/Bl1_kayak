# pipeline.py (ex-main.py, quasi inchangé, juste wrappé dans une fonction)
import os
import sys
from pathlib import Path
import pandas as pd
import argparse
import logging
from datetime import date

from sqlalchemy import create_engine
from sqlalchemy.types import (
    Integer, BigInteger, SmallInteger, Float, Numeric, String, Text,
    Boolean, Date, DateTime,
)
from sqlalchemy import inspect, text 

import config_kayak
from config_kayak import (
    AWS_BUCKET_NAME, AWS_BUCKET_DIR, DATA_DIR_CSV, 
    
)
from load_cities import load_cities, get_coordinates_cities
from get_weather_forecasts import (
    get_weather_data_for_cities, 
    select_best_weather_cities, run_weather_searches)
from scrap_hotels import collect_cities_hotels, select_top_hotels
from s3_utils import save_csv_to_s3, timestamped_filename, read_csv_from_s3
from rds_utils import get_rds_engine, save_df_to_rds, get_pg_engine

from availability import (
    build_date_windows, run_hotel_searches, keys_from_df, DEFAULT_OCCUPANCY,
    make_key, to_date, pipeline_lock, PipelineBusy,
)
CHECKIN_DATE_NR = 1
CHECKOUT_DATE_NR = -1

SRC_DIR = Path(__file__).resolve().parent
BASE_DIR = SRC_DIR.parent
os.chdir(BASE_DIR)
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))



# Types SQL cibles, par colonne (adapte aux noms de tes colonnes)
DTYPES_CITIES = {
    "city_id":           Text(),
    "city":              Text(),
    "city_lat":          Float(),
    "city_lon":          Float(),
    "city_name_":        Text(),
    "city_plus":         Text(),
}

DTYPES_HOTELS = {
    "city_id":           Text(),
    "city":              String(100),
    "city_name_":        Text(),
    "checkin_date":      Date(),
    "checkout_date":     Date(),
    "n_adults":          SmallInteger(),
    "n_children":        SmallInteger(),
    "n_rooms":           SmallInteger(),
    "scraped_at":        DateTime(),

    "hotel_name":        Text(),
    "url_hotel":         Text(),
    "address_hotel":     Text(),
    "hotel_city":        Text(),
    "hotel_description": Text(),
    "room_description":  Text(),
    "lat_hotel":         Float(),
    "lon_hotel":         Float(),
  
    "score_hotel":       Numeric(10, 2),
    "price_hotel":       Numeric(10, 2),
    "currency_hotel":    Text(),
    "combined_score_hotel": Numeric(10, 2),
}

DTYPES_WEATHER = {
    "city_id":           Text(),
    "city":              Text(),
    #"city_name_":        Text(),
    "checkin_date":      Date(),
    "checkout_date":     Date(),
    "scraped_at":        DateTime(),
    "avg_comfort_score": Numeric(5, 2),
    "temp":              Numeric(4, 2),
    "humidity":          Numeric(5, 2),
    "wind_speed_max":    Numeric(10, 2),
    "clear_slots":       Integer(),
    "rain_slots":        Integer(),
    "rain_sum":          Numeric(10, 2),
    "selected":          Integer(),
    "lat":               Float(),
    "lon":               Float(),
}
# adds parameters for manual search:
# -----------------------------------------------------------
logger = logging.getLogger("pipeline")

# Codes de sortie lus par scheduler.py et live_search.py
EXIT_OK, EXIT_ERROR, EXIT_EMPTY, EXIT_EXISTS, EXIT_BUSY = 0, 1, 2, 3, 4

DEFAULT_MAX_RESULTS = 6
DEFAULT_MAX_PRICE = 300.0
DEFAULT_TOP_CITIES = 5
MAX_NIGHTS = 14          # garde-fou pour la recherche manuelle

HOTELS_RENAME = {
    "url": "url_hotel", "address": "address_hotel", "latitude": "lat_hotel",
    "longitude": "lon_hotel", "score": "score_hotel", "price": "price_hotel",
    "currency": "currency_hotel", "combined_score": "combined_score_hotel",
}
CITIES_COLS = ["city_id", "city", "city_lat", "city_lon", "city_name_", "city_plus"]
HOTELS_COLS = [
    "city_id", "city", "city_name_", "checkin_date", "checkout_date", "n_adults", "n_children",
    "n_rooms", "scraped_at", "hotel_name", "url_hotel", "address_hotel", "hotel_city",
    "hotel_description", "lat_hotel", "lon_hotel", "score_hotel", "price_hotel",
    "currency_hotel", "room_description", "combined_score_hotel",
]
# Seules ces colonnes sont obligatoires : une description absente n'élimine plus l'hôtel
HOTELS_REQUIRED = ["city_id", "hotel_name", "checkin_date", "checkout_date",
                   "price_hotel", "score_hotel"]
WEATHER_COLS = [
    "city_id", "city", "checkin_date", "checkout_date", "scraped_at", "avg_comfort_score",
    "temp", "humidity", "wind_speed_max", "clear_slots", "rain_slots", "rain_sum",
    "selected", "city_lat", "city_lon",
]
WEATHER_RENAME = {"city_lat": "lat", "city_lon": "lon"}

# Colonnes qui identifient une « fenêtre » dans chaque table
_WINDOW_KEYS = {
    "hotels": ["checkin_date", "checkout_date", "n_adults", "n_children", "n_rooms"],
    "weather": ["checkin_date", "checkout_date"],
}
_DATE_COLS = {"checkin_date", "checkout_date"}
_SQL_KEYS = ("SELECT DISTINCT checkin_date, checkout_date, n_adults, n_children, n_rooms "
             "FROM hotels")

# ----------------------

def sauver_df(df: pd.DataFrame, table: str, engine, dtypes: dict,
              if_exists: str = "append") -> None:
    """Écrit df en base en forçant les types SQL, avec conversions pandas préalables."""
    out = df.copy()

    # Conversions pandas : sinon une colonne 'object' peut partir en TEXT malgré le dtype
    for col, typ in dtypes.items():
        if col not in out.columns:
            continue
        if isinstance(typ, Date):
            out[col] = pd.to_datetime(out[col]).dt.date
        elif isinstance(typ, DateTime):
            out[col] = pd.to_datetime(out[col])
        elif isinstance(typ, (Integer, SmallInteger, BigInteger)):
            out[col] = pd.to_numeric(out[col], errors="coerce").astype("Int64")  # entier nullable
        elif isinstance(typ, (Float, Numeric)):
            out[col] = pd.to_numeric(out[col], errors="coerce")

    # On ne garde dans dtype que les colonnes présentes (sinon erreur)
    dtype_utile = {c: t for c, t in dtypes.items() if c in out.columns}
    out.to_sql(table, engine, if_exists=if_exists, index=False,
               dtype=dtype_utile, method="multi", chunksize=1000)

# -----------------------------------------------------------
# adds functions for manual search:
# -----------------------------------------------------------

def _s3_safe(df: pd.DataFrame, filename: str) -> None:
    """Copie S3 facultative : un échec S3 ne doit pas faire perdre un run complet."""
    try:
        save_csv_to_s3(df, filename)
    except Exception as e:
        logger.warning("Copie S3 impossible (%s) : %s", filename, e)


def validate_window(ci: date, co: date) -> None:
    if co <= ci:
        raise ValueError(f"Le check-out ({co}) doit être après le check-in ({ci})")
    if (co - ci).days > MAX_NIGHTS:
        raise ValueError(f"Séjour limité à {MAX_NIGHTS} nuits (reçu {(co - ci).days})")
    if ci < date.today():
        raise ValueError(f"Check-in dans le passé : {ci}")


def read_existing_keys(engine) -> set:
    """Recherches déjà en base. Lève une erreur si la base est injoignable (échec rapide)."""
    if not inspect(engine).has_table("hotels"):
        return set()
    return keys_from_df(pd.read_sql(text(_SQL_KEYS), engine))


def get_cities_df(refresh: bool) -> pd.DataFrame:
    """Villes + coordonnées.

    refresh=False (recherche manuelle) : relit le dernier cities.csv (local, puis S3),
    sans refaire le géocodage. Sinon, ou en cas d'échec : géocodage complet comme avant.
    """
    local = Path(DATA_DIR_CSV) / "cities.csv"
    if not refresh:
        try:
            if local.exists():
                df = pd.read_csv(local, encoding="utf-8")
            else:
                df = read_csv_from_s3(AWS_BUCKET_NAME, f"{AWS_BUCKET_DIR}/cities.csv",
                                      sep=",", encoding="utf-8")
            if not df.empty and {"city_name", "lat", "lon"} <= set(df.columns):
                return df
        except Exception as e:
            logger.warning("cities.csv indisponible (%s) : géocodage complet", e)

    df = get_coordinates_cities(load_cities())
    local.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(local, index=False, encoding="utf-8")
    _s3_safe(df, "cities.csv")
    return df


def merge_cities_hotels(top_cities: pd.DataFrame, hotels_all: pd.DataFrame) -> pd.DataFrame:
    """Rattache les hôtels aux villes SUR (ville, check-in, check-out).

    L'ancienne jointure sur la seule ville dupliquait les hôtels d'une ville présente dans
    plusieurs fenêtres, avec les dates de l'autre fenêtre.
    """
    t, h = top_cities.copy(), hotels_all.copy()
    for d in (t, h):
        d["_ci"] = d["checkin_date"].map(to_date)
        d["_co"] = d["checkout_date"].map(to_date)
    h = h.drop(columns=["checkin_date", "checkout_date"])

    merged = t.merge(
        h, how="outer",
        left_on=["city_name_", "_ci", "_co"], right_on=["city", "_ci", "_co"],
        suffixes=["_city", "_hotel"],
    ).drop(columns=["_ci", "_co"])

    merged = merged.sort_values("combined_score_hotel", ascending=False)
    return (merged.rename(columns={"city_city": "city", "scraped_at_city": "scraped_at"})
                  .drop(columns=["city_hotel"]))


def hotels_csv_path(key, scraped_dt: pd.Timestamp) -> Path:
    """Nom du CSV d'une recherche manuelle : fenêtre + occupation + horodatage.

    L'horodatage est EXACTEMENT la valeur de `scraped_at` écrite en base, donc le fichier
    et les lignes se retrouvent l'un depuis l'autre, même après plusieurs recherches.
    """
    occ = f"{key.n_adults}a{key.n_children}c{key.n_rooms}r"
    nom = (f"hotels_manual_{key.checkin:%Y%m%d}_{key.checkout:%Y%m%d}_{occ}_"
           f"{scraped_dt:%Y%m%d_%H%M%S}.csv")
    return Path(DATA_DIR_CSV) / nom


def replace_windows(df: pd.DataFrame, table: str, dtypes: dict, conn) -> int:
    """Supprime UNIQUEMENT les fenêtres présentes dans df, puis ajoute df (append).

    À appeler dans une transaction (`with engine.begin() as conn`) : tout ou rien.
    Les autres fenêtres de la table ne sont jamais touchées.
    """
    if table not in _WINDOW_KEYS:
        raise ValueError(f"Table non gérée : {table}")
    if df is None or df.empty:
        return 0
    cles = _WINDOW_KEYS[table]
    manquantes = [c for c in cles if c not in df.columns]
    if manquantes:
        raise KeyError(f"{table} : colonnes de fenêtre manquantes {manquantes}")

    if inspect(conn).has_table(table):
        # CAST : fonctionne aussi si une ancienne table a des dates stockées en texte
        where = " AND ".join(
            f"CAST({c} AS date) = :{c}" if c in _DATE_COLS else f"{c} = :{c}" for c in cles
        )
        stmt = text(f"DELETE FROM {table} WHERE {where}")   # table et colonnes : constantes du code
        for ligne in df[cles].drop_duplicates().to_dict("records"):
            conn.execute(stmt, {c: (to_date(v) if c in _DATE_COLS else int(v))
                                for c, v in ligne.items()})
    sauver_df(df, table, conn, dtypes, if_exists="append")
    return len(df)


# -----------------------------------------------------------
# Utilisation
# -----------------------------------------------------------


# *** 

def run_pipeline(
    n_adults: int | None = None,
    n_children: int | None = None,
    n_rooms: int | None = None,
    max_results: int = DEFAULT_MAX_RESULTS,
    max_price: float = DEFAULT_MAX_PRICE,
    force: bool = False,
    window: tuple | None = None,
    top_n_cities: int = DEFAULT_TOP_CITIES,
) -> dict:
    """Pipeline : villes -> météo -> hôtels -> CSV -> base SQL.

    window=None            : run complet planifié (fenêtres standard, tables météo/villes remplacées).
    window=(checkin, out)  : recherche manuelle : météo relancée, UNE fenêtre, aucune autre
                             donnée de la base n'est supprimée, CSV horodaté dédié.
    Occupation non précisée -> DEFAULT_OCCUPANCY (les anciennes valeurs 2/3/2 n'étaient pas utilisées).
    Retourne un résumé avec une clé "status" : "ok" | "empty" | "exists".
    """
    # 0 : get occupancy : 
    occupancy = {
        "n_adults": DEFAULT_OCCUPANCY["n_adults"] if n_adults is None else int(n_adults),
        "n_children": DEFAULT_OCCUPANCY["n_children"] if n_children is None else int(n_children),
        "n_rooms": DEFAULT_OCCUPANCY["n_rooms"] if n_rooms is None else int(n_rooms),
    }

    # 0.bis : init 
    
    manual = window is not None
    scraped_dt = pd.Timestamp.now().floor("s")  # id for run (base AND name of CSV file)
    engine = get_pg_engine()
    
    # 1. get cities and get coord & save to s3
    try:
        existing = read_existing_keys(engine)

        # --- Recherche manuelle : validation, et sortie rapide si déjà en base
        if manual:
            ci, co = to_date(window[0]), to_date(window[1])
            validate_window(ci, co)
            key = make_key(ci, co, **occupancy)
            if key in existing and not force:
                logger.info("Fenêtre déjà en base : %s", key)
                return {"status": "exists", "key": str(key)}
            
        # 1. get cities and get coord
        df_cities = get_cities_df(refresh=not manual)

        # 2. get weather (5 days) : reloaded
        result_weather = get_weather_data_for_cities(df_cities, scraped_dt=scraped_dt)
        result_weather["scraped_at"] = scraped_dt

        # 3. dates window 
        if manual:
            jours = {to_date(d) for d in result_weather["date"].unique()}
            if ci not in jours or co not in jours:
                raise ValueError(f"Dates hors prévisions météo ({min(jours)} → {max(jours)})")
            windows = [(ci, co)]
        else:
            windows = build_date_windows(result_weather["date"].unique())

        top_cities = run_weather_searches(
            result_weather, windows,
            select_weather_cities_fn=select_best_weather_cities,
            scraped_dt=scraped_dt, top_n=top_n_cities,
        )
        if top_cities is None or top_cities.empty:
            logger.warning("Aucune ville retenue par la météo")
            return {"status": "empty", "n_hotels": 0}

        top_cities = top_cities.merge(
            df_cities.drop(columns=["lat", "lon"]), how="left",
            left_on="city", right_on="city_name",
        )
        top_cities = top_cities.drop(columns=["city_name"]).rename(
            columns={"lat": "lat_city", "lon": "lon_city"}
        )
        if not manual:
            top_cities.to_csv(os.path.join(DATA_DIR_CSV, "top_weather_cities.csv"),
                              index=False, encoding="utf-8")
            _s3_safe(top_cities, timestamped_filename("weather_top_cities"))

        # 4. hôtels
        hotels_all, failed = run_hotel_searches(
            top_cities, windows, occupancy,
            collect_fn=collect_cities_hotels, select_fn=select_top_hotels,
            skip_keys=existing, max_results=max_results, max_price=max_price,
            scraped_dt=scraped_dt, force=force,
        )
        if failed:
            logger.warning("Recherches en échec : %s", failed)
        if hotels_all is None or hotels_all.empty:
            if manual and failed:
                raise RuntimeError(f"La recherche a échoué : {failed}")
            logger.info("Rien de nouveau à enregistrer : arrêt.")
            return {"status": "empty", "n_hotels": 0, "n_failed": len(failed)}

        hotels_all = hotels_all.rename(columns=HOTELS_RENAME)
        hotels_all["scraped_at"] = scraped_dt
        if not manual:
            _s3_safe(hotels_all, timestamped_filename("hotels_windows"))   # datalake


        # 5. fusion villes/hôtels puis CSV (nom personnalisé en mode manuel)
        merged = merge_cities_hotels(top_cities, hotels_all)
        merged["scraped_at"] = scraped_dt
        if manual:
            csv_path = hotels_csv_path(key, scraped_dt)
            s3_name = csv_path.name
        else:
            csv_path = Path(DATA_DIR_CSV) / "hotels_top20_cities.csv"
            s3_name = "hotels_top20cities.csv"
        csv_path.parent.mkdir(parents=True, exist_ok=True)
        merged.to_csv(csv_path, index=False, encoding="utf-8")
        _s3_safe(merged, s3_name)
        logger.info("CSV : %s", csv_path)

        # Relecture du CSV local : ce qui est en base est exactement ce qui est dans le fichier
        df = pd.read_csv(csv_path, encoding="utf-8")
        df_cities2 = df[CITIES_COLS].dropna().drop_duplicates()
        df_hotels2 = df[HOTELS_COLS].dropna(subset=HOTELS_REQUIRED).drop_duplicates()
        df_weather2 = df[WEATHER_COLS].rename(columns=WEATHER_RENAME).dropna().drop_duplicates()
        if df_hotels2.empty:
            logger.warning("Aucune ligne d'hôtel exploitable après nettoyage")
            return {"status": "empty", "n_hotels": 0, "csv": str(csv_path)}

        # 6. base SQL : une seule transaction (tout ou rien)
        with engine.begin() as conn:
            if manual:
                replace_windows(df_weather2, "weather", DTYPES_WEATHER, conn)   # cette fenêtre seulement
            else:
                sauver_df(df_cities2, "cities", conn, DTYPES_CITIES, if_exists="replace")
                sauver_df(df_weather2, "weather", conn, DTYPES_WEATHER, if_exists="replace")
            replace_windows(df_hotels2, "hotels", DTYPES_HOTELS, conn)          # jamais de replace global

        return {
            "status": "ok", "mode": "manual" if manual else "full",
            "scraped_at": str(scraped_dt), "csv": str(csv_path),
            "n_cities": len(df_cities2), "n_hotels": len(df_hotels2), "n_weather": len(df_weather2),
        }
    finally:
        engine.dispose()   



def import_hotels_csv(path: str) -> int:
    """Réimporte en base un CSV de recherche manuelle (récupération après un échec SQL)."""
    df = pd.read_csv(path, encoding="utf-8")
    manquantes = [c for c in HOTELS_COLS if c not in df.columns]
    if manquantes:
        raise KeyError(f"CSV incompatible, colonnes manquantes : {manquantes}")
    df_hotels2 = df[HOTELS_COLS].dropna(subset=HOTELS_REQUIRED).drop_duplicates()
    engine = get_pg_engine()
    try:
        with engine.begin() as conn:
            return replace_windows(df_hotels2, "hotels", DTYPES_HOTELS, conn)
    finally:
        engine.dispose()


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Pipeline Kayak (sans argument : run complet)")
    p.add_argument("--checkin"); p.add_argument("--checkout")
    p.add_argument("--adults", type=int); p.add_argument("--children", type=int)
    p.add_argument("--rooms", type=int)
    p.add_argument("--max-price", type=float, default=DEFAULT_MAX_PRICE)
    p.add_argument("--max-results", type=int, default=DEFAULT_MAX_RESULTS)
    p.add_argument("--top-cities", type=int, default=DEFAULT_TOP_CITIES)
    p.add_argument("--force", action="store_true", help="remplace la fenêtre si elle existe déjà")
    p.add_argument("--import-csv", metavar="FICHIER", help="réimporte un CSV de recherche manuelle")
    return p.parse_args()


def main() -> int:
    args = parse_args()
    if args.import_csv:
        n = import_hotels_csv(args.import_csv)
        logger.info("%d lignes importées depuis %s", n, args.import_csv)
        return EXIT_OK if n else EXIT_EMPTY
    if bool(args.checkin) != bool(args.checkout):
        logger.error("--checkin et --checkout vont ensemble")
        return EXIT_ERROR

    window = (args.checkin, args.checkout) if args.checkin else None
    summary = run_pipeline(
        n_adults=args.adults, n_children=args.children, n_rooms=args.rooms,
        max_results=args.max_results, max_price=args.max_price,
        force=True if window is None else args.force,   # run complet : comme avant (force=True)
        window=window, top_n_cities=args.top_cities,
    )
    logger.info("Résumé : %s", summary)
    status = summary.get("status")
    if status == "ok" or (status == "empty" and window is None):
        return EXIT_OK
    return {"empty": EXIT_EMPTY, "exists": EXIT_EXISTS}.get(status, EXIT_ERROR)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [pipeline] %(message)s")
    try:
        with pipeline_lock():            # un seul pipeline à la fois (planifié ou bouton)
            code = main()
    except PipelineBusy:
        logger.warning("Un pipeline est déjà en cours : abandon.")
        code = EXIT_BUSY
    except Exception:
        logger.exception("Échec du pipeline")
        code = EXIT_ERROR
    sys.exit(code)