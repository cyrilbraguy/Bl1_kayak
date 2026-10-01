# ====================================================================
# Kayak project Cyril 
# module s3_utils : 
# s3_utils.py
# (c) 2026-09-20 
# ====================================================================
"""
Sauvegarde d'un CSV sur le bucket S3 "kayak-cyril", dans le répertoire /kayak.

Prérequis :
    pip install boto3
Identifiants AWS : via ~/.aws/credentials, variables d'environnement
(AWS_ACCESS_KEY_ID / AWS_SECRET_ACCESS_KEY / AWS_SESSION_TOKEN), ou un profil
nommé passé en argument. Aucune clé en dur dans ce fichier.
"""
from __future__ import annotations

import io
import os
from dotenv import load_dotenv
import logging
import pandas as pd
from datetime import datetime
from pathlib import Path
from typing import Optional, Union

import boto3
from botocore.exceptions import BotoCoreError, ClientError, NoCredentialsError

# s3_utils.py

logger = logging.getLogger(__name__)


from config_kayak import (
    AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY,
    AWS_BUCKET_NAME, AWS_BUCKET_DIR,
    AWS_REGION,
    )

try:
    import pandas as pd
    _PANDAS_AVAILABLE = True
except ImportError:
    _PANDAS_AVAILABLE = False


def save_csv_to_s3(
    data: Union[str, "pd.DataFrame"],
    filename: str,
    bucket: str = AWS_BUCKET_NAME,
    prefix: str = AWS_BUCKET_DIR,
    index: bool = False,
    aws_profile: Optional[str] = None,
) -> str:
    """
    Sauvegarde un CSV sur S3, dans {bucket}/{prefix}/{filename}.

    `data` accepte deux formes :
    - chemin local (str) vers un .csv déjà écrit sur disque -> upload direct
    - DataFrame pandas -> converti en CSV en mémoire, sans fichier temporaire

    Retourne l'URI S3 (s3://bucket/key) de l'objet créé.

    Lève :
    - ValueError si `filename` ne se termine pas par '.csv'
    - FileNotFoundError si `data` est un chemin de fichier inexistant
    - RuntimeError en cas d'échec d'upload (identifiants AWS manquants,
      permissions insuffisantes, bucket inexistant...)
    """
    if not filename.endswith(".csv"):
        raise ValueError("filename doit se terminer par '.csv'")

    key = f"{prefix.strip('/')}/{filename}"
    session = boto3.Session(profile_name=aws_profile) if aws_profile else boto3.Session()
    s3 = session.client("s3")

    try:
        if isinstance(data, str):
            local_path = Path(data)  # gère nativement les séparateurs Windows/macOS/Linux
            if not local_path.is_file():
                raise FileNotFoundError(f"Fichier introuvable : {data}")
            s3.upload_file(str(local_path), bucket, key)
        elif _PANDAS_AVAILABLE and isinstance(data, pd.DataFrame):
            buffer = io.StringIO()
            data.to_csv(buffer, index=index)
            s3.put_object(Bucket=bucket, Key=key, Body=buffer.getvalue().encode("utf-8"))
        else:
            raise TypeError(f"type de `data` non supporté : {type(data)} (attendu str ou pandas.DataFrame)")
    except NoCredentialsError:
        raise RuntimeError(
            "Identifiants AWS introuvables. Configure ~/.aws/credentials, les "
            "variables d'environnement AWS_ACCESS_KEY_ID/AWS_SECRET_ACCESS_KEY, "
            "ou passe aws_profile=<nom_du_profil>."
        )
    except (BotoCoreError, ClientError) as e:
        raise RuntimeError(f"Échec de l'upload S3 (bucket={bucket}, key={key}) : {e}")

    uri = f"s3://{bucket}/{key}"
    logger.info("CSV sauvegardé sur %s", uri)
    return uri


def timestamped_filename(base_name: str, ext: str = "csv") -> str:
    """Utilitaire : génère un nom de fichier horodaté pour éviter d'écraser
    un upload précédent. Ex. timestamped_filename("hotels") -> 'hotels_20260923_143012.csv'."""
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    return f"{base_name}_{ts}.{ext.lstrip('.')}"


def read_csv_from_s3(
    bucket: str,
    key: str,
    *,
    profile: str | None = None,
    region: str | None = None,
    **read_csv_kwargs,
) -> pd.DataFrame:
    """Charge un CSV depuis S3 dans un DataFrame.

    Les credentials sont résolus par boto3 (variables d'env, ~/.aws/credentials, rôle IAM...).
    Les kwargs supplémentaires sont transmis à pd.read_csv (sep, encoding, dtype, ...).
    """
    if not bucket or not key:
        raise ValueError("bucket et key sont obligatoires")

    try:
        session = boto3.Session(profile_name=profile, region_name=region)
        s3 = session.client("s3")
        obj = s3.get_object(Bucket=bucket, Key=key)
        body = obj["Body"].read()  # bytes
    except NoCredentialsError:
        raise RuntimeError(
            "Credentials AWS introuvables. Définis AWS_ACCESS_KEY_ID / AWS_SECRET_ACCESS_KEY "
            "ou configure un profil (aws configure)."
        ) from None
    except ClientError as e:
        code = e.response.get("Error", {}).get("Code", "")
        if code in ("NoSuchKey", "404"):
            raise FileNotFoundError(f"s3://{bucket}/{key} introuvable") from None
        if code in ("AccessDenied", "403"):
            raise PermissionError(f"Accès refusé à s3://{bucket}/{key}") from None
        if code == "NoSuchBucket":
            raise FileNotFoundError(f"Bucket inexistant : {bucket}") from None
        raise
    except BotoCoreError as e:
        raise RuntimeError(f"Erreur réseau/boto3 : {e}") from e

    if not body:
        raise ValueError(f"Fichier vide : s3://{bucket}/{key}")

    try:
        df = pd.read_csv(io.BytesIO(body), **read_csv_kwargs)
    except pd.errors.EmptyDataError:
        raise ValueError(f"CSV sans colonnes : s3://{bucket}/{key}") from None

    logger.info("Chargé s3://%s/%s : %d lignes, %d colonnes", bucket, key, *df.shape)
    return df


if __name__ == "__main__":
    # Exemple avec un DataFrame en mémoire
    import pandas as pd

    df = pd.DataFrame({"city": ["Lyon", "Annecy"], "score": [8.5, 9.1]})
    uri = save_csv_to_s3(df, timestamped_filename("hotels"))
    print(f"Uploadé : {uri}")

    # Exemple avec un fichier CSV déjà présent sur disque
    # uri = save_csv_to_s3("hotels_lyon.csv", "hotels_lyon.csv")




