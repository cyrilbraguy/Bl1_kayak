# ====================================================================
# Kayak project Cyril 
# module rds_utils : 
# rds_utils.py
# (c) 2026-09-20 
# ====================================================================

# rds_utils.py
from __future__ import annotations
import os

import logging
from urllib.parse import quote_plus

import pandas as pd
from sqlalchemy import create_engine
from sqlalchemy.exc import SQLAlchemyError

logger = logging.getLogger(__name__)

from config_kayak import (
    WEATHER_API_KEY, AWS_ACCESS_KEY, AWS_SECRET_ACCESS_KEY,
    AWS_BUCKET_NAME, AWS_BUCKET_DIR,
    AWS_DB_NAME, AWS_DB_USER, AWS_DB_PASS, AWS_REGION,
    RDSHOST,DATABASE_URL
)



def get_pg_engine(database_url: str | None = None):
    """Engine Postgres (Neon, RDS, local) depuis DATABASE_URL, avec SSL et tolérance au démarrage à froid."""
    url = database_url or DATABASE_URL
    if not url:
        raise ValueError("DATABASE_URL absente (variable d'environnement ou paramètre)")
    if url.startswith("postgres://"):
        url = "postgresql://" + url[len("postgres://"):]
    if url.startswith("postgresql://"):
        url = url.replace("postgresql://", "postgresql+psycopg2://", 1)  # force le driver psycopg2

    return create_engine(
        url,
        pool_pre_ping=True,        # revalide la connexion (le compute a pu se suspendre)
        pool_recycle=300,          # recycle avant les coupures côté serveur
        connect_args={"connect_timeout": 30, "sslmode": "require"},  # 30 s : marge pour le réveil
    )

def get_rds_engine(
    host: str,
    database: str,
    user: str,
    password: str,
    *,
    port: int = 5432,
    driver: str = "postgresql+psycopg2",  # "mysql+pymysql" pour MySQL
    ):
    """Crée un engine SQLAlchemy vers RDS. Le mot de passe est échappé (caractères spéciaux)."""
    if not all([host, database, user, password]):
        raise ValueError("host, database, user et password sont obligatoires")

    pwd_escaped = quote_plus(password)  # gère les caractères type @, /, : dans le mdp
    url = f"{driver}://{user}:{pwd_escaped}@{host}:{port}/{database}"
    return create_engine(url, pool_pre_ping=True)  # pool_pre_ping : évite les connexions mortes


def save_df_to_rds(
    df: pd.DataFrame,
    table_name: str,
    engine,
    *,
    if_exists: str = "replace",  # "replace" | "append" | "fail"
    chunksize: int = 5000,
    index: bool = False,
    ) -> None:
    """Écrit un DataFrame dans une table RDS."""
    if df.empty:
        raise ValueError("DataFrame vide, rien à sauvegarder")
    if if_exists not in ("replace", "append", "fail"):
        raise ValueError("if_exists doit valoir 'replace', 'append' ou 'fail'")

    try:
        df.to_sql(
            table_name,
            con=engine,
            if_exists=if_exists,
            index=index,
            chunksize=chunksize,  # évite de tout envoyer d'un coup sur gros volumes
            method="multi",       # insert en batch, plus rapide
        )
    except SQLAlchemyError as e:
        raise RuntimeError(f"Échec de l'écriture dans '{table_name}' : {e}") from e

    logger.info("Table '%s' écrite : %d lignes", table_name, len(df))