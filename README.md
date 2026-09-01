# 🏥 Projet 5 : Pipeline ETL de Données de Santé (S3 vers MongoDB & CI/CD)

Ce projet implémente un pipeline ETL (Extract, Transform, Load) robuste permettant d'extraire, nettoyer, transformer et migrer des données de santé depuis un stockage objet cloud (Amazon S3 / Data Lake) vers une base de données NoSQL (MongoDB). L'ensemble de l'infrastructure est conteneurisé via Docker et sécurisé par des tests unitaires et un pipeline d'intégration continue (CI) avec GitHub Actions.

## 📂 Architecture du Projet

Le projet suit une structure stricte pour séparer l'intégration continue, la base de données et la logique de traitement :

```text
Projet_5/
├── .github/
│   └── workflows/
│       └── ci.yml             # Workflow d'intégration continue GitHub Actions
├── .env                       # Fichier des variables d'environnement (non versionné)
├── docker-compose.yml         # Orchestration des conteneurs (Mongo + Python)
└── migration/                 
    ├── Dockerfile             # Instructions de construction de l'image ETL
    ├── main.py                # Script Python contenant la logique ETL (S3 -> Mongo)
    ├── test_main.py           # Suite de tests unitaires (pytest)
    └── requirements.txt       # Dépendances du projet (boto3, pandas, pymongo, pytest...)

```

## 🚀 Comment lancer la migration

### 1. Prérequis

Assurez-vous d'avoir installé **Docker** et **Docker Compose** sur votre machine.

### 2. Configuration

Créez un fichier `.env` à la racine du projet pour configurer les accès sécurisés à la base de données et les clés AWS :

```env
# --- Identifiants ROOT (Administration système) ---
MONGO_INITDB_ROOT_USERNAME=admin
MONGO_INITDB_ROOT_PASSWORD=password

# --- Identifiants APPLICATION (Script de migration - ReadWrite) ---
APP_USER=app_migration_user
APP_PASSWORD=migration_password_123

# --- Identifiants CONSULTATION (Médecin/Analyste - ReadOnly) ---
READ_ONLY_USER=doctor_viewer
READ_ONLY_PASSWORD=viewer_password_456

# --- Identifiants AWS S3 (Data Lake) ---
AWS_ACCESS_KEY_ID=ton_access_key
AWS_SECRET_ACCESS_KEY=ton_secret_key
AWS_DEFAULT_REGION=eu-west-3
S3_BUCKET_NAME=nom-de-ton-bucket
S3_PREFIX=landing/

```

### 3. Exécution

Ouvrez un terminal à la racine du projet et lancez la commande suivante pour construire l'image et démarrer les services :

```bash
docker-compose up --build

```

*Le script Python exécutera automatiquement l'ingestion depuis S3, le nettoyage et la migration, puis le conteneur s'arrêtera, tandis que la base de données MongoDB continuera de tourner en arrière-plan.*

---

## ⚙️ Que se passe-t-il pendant la migration ?

Le script `main.py` exécute un traitement par lots (Batch Processing) divisé en trois grandes étapes garantissant l'intégrité et la qualité des données.

### Étape 1 : Extraction (AWS S3) et Transformation (Nettoyage)

* **Ingestion S3 en mémoire :** Connexion au bucket via `boto3`, filtrage des fichiers selon leur nom (`healthcare_*.csv`) et chargement direct du flux binaire en mémoire via `io.BytesIO` pour éviter toute écriture disque inutile.
* **Filtrage des données critiques :** Suppression des lignes contenant des valeurs manquantes sur les colonnes obligatoires (`Name`, `Age`, `Medical Condition`, `Date of Admission`).
* **Filtrage des anomalies :** Suppression des âges aberrants (strictement compris entre 0 et 120 ans).
* **Gestion des décimales :** Toutes les colonnes numériques flottantes sont arrondies à 2 décimales pour garantir une précision financière standardisée.
* **Audit des valeurs manquantes :** Le script scanne et signale la présence de valeurs nulles restantes.
* **Déduplication métier :** Les patients en doublon sont identifiés et purgés via une clé composite basée sur `Name`, `Age` et `Blood Type`.
* **Harmonisation textuelle :** La colonne `Name` est reformatée en « Format Titre » (ex: *JEAN DUPONT* devient *Jean Dupont*).
* **Normalisation temporelle :** Conversion des colonnes de dates avec tolérance aux formats invalides (`errors="coerce"`).

### Étape 2 : Chargement (Load)

Une fois les données certifiées propres, le pipeline prépare l'insertion dans MongoDB :

* **Idempotence :** La collection `patients` de la base `healthcare_db` est purgée avant l'insertion.
* **Insertion en bloc :** Les données sont converties en dictionnaires et injectées via `insert_many`.
* **Indexation :** Création d'index sur les champs `Name` et `Date of Admission` pour accélérer les futures requêtes.
* **Vérification comptable :** Le script compare le nombre de lignes du jeu de données nettoyé avec le nombre de documents réellement insérés dans MongoDB.

### Étape 3 : Observabilité et Contrôle Qualité

Une fois la migration terminée, un audit post-insertion est déclenché directement depuis MongoDB :

* **Vérification du typage :** Le script analyse les documents pour confirmer que MongoDB a correctement interprété les types de données (ex: *str*, *float*, *int*, *datetime*).

---

## 🧪 Tests Unitaires & Intégration Continue (CI/CD)

### Exécution locale des tests

La suite de tests unitaires permet de valider le comportement des fonctions de nettoyage face aux cas limites et anomalies :

```bash
pytest

```

*Les tests vérifient notamment le filtrage des âges invalides, la déduplication multi-critères, le formatage de la casse et la gestion des dates corrompues.*

---

## 📊 Visualiser les données

Pour consulter le résultat de la migration, vous pouvez vous connecter à la base de données via **MongoDB Compass** en utilisant l'URI suivante :

```text
mongodb://admin:password@localhost:27023/?authSource=admin

```

*(Modifiez `admin` et `password` selon les valeurs définies dans votre fichier `.env` si nécessaire).*
