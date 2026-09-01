// On cible la base de données médicale
const dbName = 'healthcare_db';
const db = db.getSiblingDB(dbName);

// 1. Création de l'utilisateur de MIGRATION (Lecture/Écriture)
db.createUser({
    user: process.env.APP_USER,
    pwd: process.env.APP_PASSWORD,
    roles: [{ role: 'readWrite', db: dbName }]
});

// 2. Création de l'utilisateur de CONSULTATION (Lecture seule)
db.createUser({
    user: process.env.READ_ONLY_USER,
    pwd: process.env.READ_ONLY_PASSWORD,
    roles: [{ role: 'read', db: dbName }]
});

print("Sécurité : Les utilisateurs 'ReadWrite' et 'ReadOnly' ont été créés avec succès !");