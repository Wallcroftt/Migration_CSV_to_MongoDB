FROM python:3.9-slim

WORKDIR /app

# Création du dossier qui va accueillir le volume de données
RUN mkdir -p /app/data

# Copie uniquement le code Python et les dépendances
COPY requirements.txt .
COPY main_test.py .

# Installe les dépendances
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

CMD ["python", "main_test.py"]