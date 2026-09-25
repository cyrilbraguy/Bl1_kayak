# ====================================================================
# Kayak project Cyril 
# module rds_utils : 
# rds_utils.py
# (c) 2026-09-20 
# ====================================================================

# rds_utils.py
from __future__ import annotations

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
    RDSHOST,
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