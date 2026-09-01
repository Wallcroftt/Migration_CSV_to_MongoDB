import io
import logging
import os
from collections import defaultdict

import boto3
from botocore.exceptions import ClientError
from dotenv import find_dotenv, load_dotenv
import pandas as pd
from pymongo import ASCENDING, MongoClient

# ==========================================
# CONFIGURATION DU LOGGER
# ==========================================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)


def load_and_filter_files_from_s3(
    bucket_name: str,
    prefix: str = "",
    file_pattern: str = "healthcare_",
    s3_client: boto3.client = None,
) -> pd.DataFrame | None:
    """Scanne un bucket S3, filtre les fichiers selon leur clé et leur structure,
    et retourne un DataFrame global concaténé.
    """
    if s3_client is None:
        endpoint_url = os.environ.get("AWS_ENDPOINT_URL")
        s3_client = boto3.client(
            "s3",
            endpoint_url=endpoint_url,
            aws_access_key_id=os.environ.get("AWS_ACCESS_KEY_ID"),
            aws_secret_access_key=os.environ.get("AWS_SECRET_ACCESS_KEY"),
            region_name=os.environ.get("AWS_DEFAULT_REGION", "eu-west-3"),
        )

    logging.info("=== SÉLECTION ET LECTURE DES FICHIERS DEPUIS S3 ===")
    logging.info(f"Scan du bucket : '{bucket_name}' avec le préfixe : '{prefix}'")

    try:
        response = s3_client.list_objects_v2(Bucket=bucket_name, Prefix=prefix)
    except ClientError as e:
        logging.error(f"Erreur d'accès au bucket S3 '{bucket_name}' : {e}")
        return None

    contents = response.get("Contents", [])
    if not contents:
        logging.warning(f"Aucun objet trouvé dans le bucket '{bucket_name}'.")
        return None

    required_columns = {"Name", "Age", "Medical Condition", "Date of Admission"}
    valid_dataframes = []

    for obj in contents:
        key = obj["Key"]
        filename = os.path.basename(key)

        # Filtre sur le nom et l'extension du fichier
        if not (filename.startswith(file_pattern) and filename.endswith(".csv")):
            continue

        try:
            # Récupération de l'objet binaire en mémoire
            s3_object = s3_client.get_object(Bucket=bucket_name, Key=key)
            file_stream = io.BytesIO(s3_object["Body"].read())

            temp_df = pd.read_csv(file_stream)

            # Vérification de la structure du fichier
            if not required_columns.issubset(temp_df.columns):
                logging.warning(f"Rejeté : '{key}' (colonnes obligatoires manquantes).")
                continue

            valid_dataframes.append(temp_df)
            logging.info(f"Validé : '{key}' ({len(temp_df)} lignes).")

        except Exception as e:
            logging.error(f"Erreur de lecture sur l'objet S3 '{key}' : {e}")

    if not valid_dataframes:
        logging.warning("Aucun fichier S3 n'a passé les critères de validation.")
        return None

    global_df = pd.concat(valid_dataframes, ignore_index=True)
    logging.info(f"Total des lignes chargées depuis S3 : {len(global_df)}")
    return global_df


def clean_data(data: pd.DataFrame) -> pd.DataFrame:
    """Nettoie le DataFrame, filtre les anomalies et supprime les doublons."""
    logging.info("=== NETTOYAGE ET TRANSFORMATION ===")

    # 1. Suppression des lignes avec des valeurs manquantes critiques
    critical_columns = ["Name", "Age", "Medical Condition", "Date of Admission"]
    initial_len = len(data)
    data = data.dropna(subset=critical_columns)
    dropped_na = initial_len - len(data)
    if dropped_na > 0:
        logging.warning(f"Filtrage : {dropped_na} ligne(s) avec données critiques manquantes.")

    # 2. Filtrage des aberrations numériques sur l'âge
    initial_len = len(data)
    data = data[(data["Age"] >= 0) & (data["Age"] <= 120)]
    dropped_age = initial_len - len(data)
    if dropped_age > 0:
        logging.warning(f"Filtrage : {dropped_age} ligne(s) avec âge aberrant.")

    # 3. Arrondi des flottants
    numeric_cols = data.select_dtypes(include=["float"]).columns
    for col in numeric_cols:
        data[col] = data[col].round(2)

    # 4. Détection des valeurs manquantes restantes
    missing_values = data.isnull().sum()
    missing_values = missing_values[missing_values > 0]
    if not missing_values.empty:
        logging.info(f"Valeurs manquantes non critiques sur {len(missing_values)} colonnes.")
    else:
        logging.info("Aucune valeur manquante restante.")

    # 5. Déduplication
    colonne_a_verifier = ["Name", "Age", "Blood Type"]
    initial_len = len(data)
    data = data.drop_duplicates(subset=colonne_a_verifier, keep="first").copy()
    duplicates_removed = initial_len - len(data)
    if duplicates_removed > 0:
        logging.info(f"{duplicates_removed} doublon(s) supprimé(s).")
    else:
        logging.info("Aucun doublon détecté.")

    # 6. Harmonisation de la casse
    if "Name" in data.columns:
        data["Name"] = data["Name"].apply(lambda x: x.title() if isinstance(x, str) else x)
        logging.info("Casse de 'Name' harmonisée.")

    # 7. Normalisation des formats temporels
    colonnes_dates = ["Date of Admission", "Discharge Date"]
    for col in colonnes_dates:
        if col in data.columns:
            data[col] = pd.to_datetime(data[col], errors="coerce")
            logging.info(f"Colonne '{col}' normalisée en DateTime.")

    return data


def migrate_data(data: pd.DataFrame, db_name: str, collection_name: str, client: MongoClient) -> None:
    """Insère les données dans MongoDB avec purge préalable et indexation."""
    logging.info("=== DÉBUT DE LA MIGRATION MONGODB ===")

    db = client[db_name]
    collection = db[collection_name]

    collection.drop()
    logging.info(f"Collection '{collection_name}' purgée.")

    records = data.to_dict("records")
    if records:
        result = collection.insert_many(records)
        logging.info(f"{len(result.inserted_ids)} documents insérés.")
    else:
        logging.warning("Aucun document à insérer.")

    collection.create_index([("Name", ASCENDING)], unique=False)
    collection.create_index([("Date of Admission", ASCENDING)], unique=False)

    inserted_count = collection.count_documents({})
    if len(data) == inserted_count:
        logging.info(f"Audit intégrité : Lignes = {len(data)} | Mongo = {inserted_count}.")
    else:
        logging.warning(f"Écart détecté. Lignes : {len(data)} | Mongo : {inserted_count}")


def test_data_quality_mongodb(db_name: str, collection_name: str, client: MongoClient) -> None:
    """Contrôle les types de champs présents dans la collection MongoDB."""
    db = client[db_name]
    collection = db[collection_name]

    logging.info("=== VÉRIFICATION DE LA QUALITÉ DANS MONGODB ===")
    documents = list(collection.find())
    if not documents:
        logging.warning("Aucun document trouvé dans la collection.")
        return

    field_types = defaultdict(set)
    for doc in documents:
        for field, value in doc.items():
            field_types[field].add(type(value).__name__)

    logging.info("Types stockés :")
    for field, types in field_types.items():
        logging.info(f" - '{field}' : {types}")


# ==========================================
# POINT D'ENTRÉE PRINCIPAL
# ==========================================
if __name__ == "__main__":
    load_dotenv(find_dotenv())

    # Configuration MongoDB
    url = os.environ.get("MONGO_URI")
    if not url:
        usr = os.environ.get("APP_USER")
        pwd = os.environ.get("APP_PASSWORD")
        url = f"mongodb://{usr}:{pwd}@localhost:27023/healthcare_db?authSource=healthcare_db"

    # Configuration AWS S3 / MinIO
    s3_bucket = os.environ.get("S3_BUCKET_NAME", "healthcare-datalake-raw")
    s3_prefix = os.environ.get("S3_PREFIX", "landing/")
    endpoint_url = os.environ.get("AWS_ENDPOINT_URL")

    s3_client = boto3.client(
        "s3",
        endpoint_url=endpoint_url,
        aws_access_key_id=os.environ.get("AWS_ACCESS_KEY_ID"),
        aws_secret_access_key=os.environ.get("AWS_SECRET_ACCESS_KEY"),
        region_name=os.environ.get("AWS_DEFAULT_REGION", "eu-west-3"),
    )

    logging.info("Tentative de connexion à MongoDB...")
    mongo_client = MongoClient(url)

    try:
        # 1. Extraction depuis S3 (Data Lake Landing Zone)
        raw_data = load_and_filter_files_from_s3(
            bucket_name=s3_bucket,
            prefix=s3_prefix,
            file_pattern="healthcare_",
            s3_client=s3_client,
        )

        if raw_data is not None:
            # 2. Nettoyage global
            cleaned_data = clean_data(raw_data)

            # 3. Chargement MongoDB
            migrate_data(cleaned_data, "healthcare_db", "patients", mongo_client)

            # 4. Audit qualité
            test_data_quality_mongodb("healthcare_db", "patients", mongo_client)

    except Exception as e:
        logging.error(f"Une erreur est survenue lors de l'exécution : {e}")
    finally:
        mongo_client.close()
        logging.info("Connexion MongoDB fermée.")