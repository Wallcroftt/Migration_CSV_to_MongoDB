import boto3
from moto import mock_aws
import pandas as pd
import pytest

from Migration.main import clean_data, load_and_filter_files_from_s3


def test_clean_data_age_filter():
    """Vérifie que les âges aberrants (< 0 ou > 120 ans) sont exclus."""
    raw_data = pd.DataFrame({
        "Name": ["Alice", "Bob", "Charlie"],
        "Age": [-5, 45, 250],
        "Medical Condition": ["Asthma", "Flu", "Diabetes"],
        "Date of Admission": ["2023-01-01", "2023-01-02", "2023-01-03"],
        "Blood Type": ["A+", "B+", "O-"],
        "Discharge Date": ["2023-01-10", "2023-01-11", "2023-01-12"],
    })

    cleaned_df = clean_data(raw_data)

    assert len(cleaned_df) == 1
    assert cleaned_df.iloc[0]["Name"] == "Bob"


def test_clean_data_deduplication():
    """Vérifie que les doublons sur (Name, Age, Blood Type) sont supprimés."""
    raw_data = pd.DataFrame({
        "Name": ["Jane Doe", "Jane Doe", "Unique Bob"],
        "Age": [30, 30, 45],
        "Medical Condition": ["Flu", "Flu", "Asthma"],
        "Date of Admission": ["2023-10-15", "2023-10-15", "2023-10-16"],
        "Blood Type": ["A+", "A+", "O-"],
        "Discharge Date": ["2023-10-20", "2023-10-20", "2023-10-21"],
    })

    cleaned_df = clean_data(raw_data)

    assert len(cleaned_df) == 2


def test_clean_data_date_and_case_formatting():
    """Vérifie l'harmonisation de la casse et le parsing sécurisé des dates."""
    raw_data = pd.DataFrame({
        "Name": ["jOhn dOe"],
        "Age": [40],
        "Medical Condition": ["None"],
        "Date of Admission": ["2023-99-99"],
        "Blood Type": ["B+"],
        "Discharge Date": ["2023-10-20"],
    })

    cleaned_df = clean_data(raw_data)

    assert cleaned_df.iloc[0]["Name"] == "John Doe"
    assert pd.isna(cleaned_df.iloc[0]["Date of Admission"])


@mock_aws
def test_load_and_filter_files_from_s3():
    """Simule un bucket S3 en mémoire via Moto et valide l'ingestion."""
    bucket_name = "test-datalake"
    prefix = "landing/"
    region = "eu-west-3"

    s3_client = boto3.client("s3", region_name=region)
    s3_client.create_bucket(
        Bucket=bucket_name,
        CreateBucketConfiguration={"LocationConstraint": region},
    )

    # 1. Fichier valide
    valid_csv = "Name,Age,Medical Condition,Date of Admission,Blood Type\nAlice,30,Flu,2023-01-01,A+\n"
    s3_client.put_object(Bucket=bucket_name, Key=f"{prefix}healthcare_valid.csv", Body=valid_csv)

    # 2. Fichier avec schéma invalide (colonne Name manquante)
    invalid_csv = "Age,Medical Condition,Date of Admission\n40,Cold,2023-01-02\n"
    s3_client.put_object(Bucket=bucket_name, Key=f"{prefix}healthcare_invalid.csv", Body=invalid_csv)

    # 3. Fichier hors filtre (ne commence pas par healthcare_)
    ignored_csv = "Name,Age,Medical Condition,Date of Admission\nBob,50,Diabetes,2023-01-03\n"
    s3_client.put_object(Bucket=bucket_name, Key=f"{prefix}other_data.csv", Body=ignored_csv)

    # Exécution
    result_df = load_and_filter_files_from_s3(
        bucket_name=bucket_name,
        prefix=prefix,
        file_pattern="healthcare_",
        s3_client=s3_client,
    )

    assert result_df is not None
    assert len(result_df) == 1
    assert result_df.iloc[0]["Name"] == "Alice"