"""
Initialise la base SQLite clients.db avec 50 clients fictifs.

Usage :
    python seed_db.py          # crée la base si absente, ignore si déjà peuplée
    python seed_db.py --reset  # supprime et recrée la base
"""

import sqlite3
import sys
from pathlib import Path

DB_PATH = Path(__file__).parent / "clients.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS clients (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    civilite    TEXT NOT NULL,
    prenom      TEXT NOT NULL,
    nom         TEXT NOT NULL,
    adresse     TEXT NOT NULL,
    code_postal TEXT NOT NULL,
    ville       TEXT NOT NULL,
    telephone   TEXT NOT NULL,
    email       TEXT
);
CREATE INDEX IF NOT EXISTS idx_clients_nom ON clients(nom);
"""

# (civilite, prenom, nom, adresse, code_postal, ville, telephone, email)
# Plusieurs "Martin" pour tester l'ambiguïté.
CLIENTS = [
    ("Madame",   "Isabelle",  "Martin",     "12 rue des Lilas",          "75011", "Paris",            "06 12 34 56 78", "isabelle.martin@example.fr"),
    ("Monsieur", "Jean",      "Martin",     "5 avenue du Général Leclerc","33000", "Bordeaux",         "06 23 45 67 89", "jean.martin@example.fr"),
    ("Madame",   "Sophie",    "Martin",     "27 boulevard Gambetta",     "59000", "Lille",            "07 34 56 78 90", "sophie.martin@example.fr"),
    ("Monsieur", "Pierre",    "Dupont",     "8 rue Victor Hugo",         "69003", "Lyon",             "06 45 67 89 01", "pierre.dupont@example.fr"),
    ("Madame",   "Marie",     "Bernard",    "14 impasse des Fleurs",     "31000", "Toulouse",         "06 56 78 90 12", "marie.bernard@example.fr"),
    ("Monsieur", "Luc",       "Dubois",     "3 place de la République",  "44000", "Nantes",           "07 67 89 01 23", "luc.dubois@example.fr"),
    ("Madame",   "Claire",    "Thomas",     "21 rue de la Paix",         "67000", "Strasbourg",       "06 78 90 12 34", "claire.thomas@example.fr"),
    ("Monsieur", "Paul",      "Robert",     "9 chemin du Moulin",        "13008", "Marseille",        "07 89 01 23 45", "paul.robert@example.fr"),
    ("Madame",   "Hélène",    "Petit",      "45 avenue Jean Jaurès",     "34000", "Montpellier",      "06 90 12 34 56", "helene.petit@example.fr"),
    ("Monsieur", "Antoine",   "Durand",     "17 rue du Commerce",        "06000", "Nice",             "07 01 23 45 67", "antoine.durand@example.fr"),
    ("Madame",   "Nathalie",  "Leroy",      "6 rue des Tilleuls",        "35000", "Rennes",           "06 13 24 35 46", "nathalie.leroy@example.fr"),
    ("Monsieur", "François",  "Moreau",     "32 avenue Foch",            "51100", "Reims",            "06 24 35 46 57", "francois.moreau@example.fr"),
    ("Madame",   "Sylvie",    "Simon",      "11 rue Pasteur",            "21000", "Dijon",            "07 35 46 57 68", "sylvie.simon@example.fr"),
    ("Monsieur", "Michel",    "Laurent",    "4 place du Marché",         "38000", "Grenoble",         "06 46 57 68 79", "michel.laurent@example.fr"),
    ("Madame",   "Christine", "Lefebvre",   "28 rue Saint-Michel",       "76000", "Rouen",            "07 57 68 79 80", "christine.lefebvre@example.fr"),
    ("Monsieur", "Philippe",  "Michel",     "19 avenue de la Liberté",   "54000", "Nancy",            "06 68 79 80 91", "philippe.michel@example.fr"),
    ("Madame",   "Valérie",   "Garcia",     "7 rue des Acacias",         "87000", "Limoges",          "07 79 80 91 02", "valerie.garcia@example.fr"),
    ("Monsieur", "Olivier",   "David",      "15 rue du Général de Gaulle","49000", "Angers",          "06 80 91 02 13", "olivier.david@example.fr"),
    ("Madame",   "Véronique", "Bertrand",   "22 rue de Verdun",          "57000", "Metz",             "07 91 02 13 24", "veronique.bertrand@example.fr"),
    ("Monsieur", "Patrick",   "Roux",       "10 allée des Érables",      "42000", "Saint-Étienne",    "06 02 13 24 35", "patrick.roux@example.fr"),
    ("Madame",   "Catherine", "Vincent",    "36 rue du Faubourg",        "63000", "Clermont-Ferrand", "07 13 24 35 46", "catherine.vincent@example.fr"),
    ("Monsieur", "Thierry",   "Fournier",   "2 rue de l'Église",         "68000", "Colmar",           "06 14 25 36 47", "thierry.fournier@example.fr"),
    ("Madame",   "Martine",   "Morel",      "18 boulevard Saint-Germain","75006", "Paris",            "07 15 26 37 48", "martine.morel@example.fr"),
    ("Monsieur", "Bernard",   "Girard",     "25 rue de la Gare",         "29000", "Quimper",          "06 16 27 38 49", "bernard.girard@example.fr"),
    ("Madame",   "Brigitte",  "André",      "13 rue des Vignes",         "84000", "Avignon",          "07 17 28 39 50", "brigitte.andre@example.fr"),
    ("Monsieur", "Alain",     "Mercier",    "40 avenue Victor Hugo",     "80000", "Amiens",           "06 18 29 40 51", "alain.mercier@example.fr"),
    ("Madame",   "Dominique", "Lambert",    "8 rue des Remparts",        "45000", "Orléans",          "07 19 30 41 52", "dominique.lambert@example.fr"),
    ("Monsieur", "Jérôme",    "Bonnet",     "16 rue Molière",            "72000", "Le Mans",          "06 20 31 42 53", "jerome.bonnet@example.fr"),
    ("Madame",   "Patricia",  "François",   "3 cours de l'Intendance",   "33000", "Bordeaux",         "07 21 32 43 54", "patricia.francois@example.fr"),
    ("Monsieur", "Frédéric",  "Martinez",   "29 rue de Strasbourg",      "64000", "Pau",              "06 22 33 44 55", "frederic.martinez@example.fr"),
    ("Madame",   "Laurence",  "Legrand",    "5 boulevard Carnot",        "73000", "Chambéry",         "07 23 34 45 56", "laurence.legrand@example.fr"),
    ("Monsieur", "Stéphane",  "Garnier",    "14 rue Nationale",          "37000", "Tours",            "06 24 35 46 57", "stephane.garnier@example.fr"),
    ("Madame",   "Sandrine",  "Faure",      "20 avenue de l'Europe",     "25000", "Besançon",         "07 25 36 47 58", "sandrine.faure@example.fr"),
    ("Monsieur", "Christophe","Rousseau",   "9 rue de la Cathédrale",    "14000", "Caen",             "06 26 37 48 59", "christophe.rousseau@example.fr"),
    ("Madame",   "Anne",      "Blanc",      "31 rue des Carmes",         "86000", "Poitiers",         "07 27 38 49 60", "anne.blanc@example.fr"),
    ("Monsieur", "Nicolas",   "Guerin",     "12 rue de la Liberté",      "83000", "Toulon",           "06 28 39 50 61", "nicolas.guerin@example.fr"),
    ("Madame",   "Chantal",   "Muller",     "6 rue de la Synagogue",     "67000", "Strasbourg",       "07 29 40 51 62", "chantal.muller@example.fr"),
    ("Monsieur", "Didier",    "Henry",      "23 rue de Paris",           "78000", "Versailles",       "06 30 41 52 63", "didier.henry@example.fr"),
    ("Madame",   "Françoise", "Roussel",    "17 rue Saint-Louis",        "56000", "Vannes",           "07 31 42 53 64", "francoise.roussel@example.fr"),
    ("Monsieur", "Pascal",    "Nicolas",    "4 place Stanislas",         "54000", "Nancy",            "06 32 43 54 65", "pascal.nicolas@example.fr"),
    ("Madame",   "Monique",   "Perrin",     "26 rue du Port",            "17000", "La Rochelle",      "07 33 44 55 66", "monique.perrin@example.fr"),
    ("Monsieur", "Julien",    "Morin",      "11 avenue de la Plage",     "85000", "Les Sables-d'Olonne", "06 34 45 56 67", "julien.morin@example.fr"),
    ("Madame",   "Corinne",   "Mathieu",    "8 rue Thiers",              "66000", "Perpignan",        "07 35 46 57 68", "corinne.mathieu@example.fr"),
    ("Monsieur", "Vincent",   "Clément",    "15 rue Lafayette",          "75009", "Paris",            "06 36 47 58 69", "vincent.clement@example.fr"),
    ("Madame",   "Nadine",    "Gauthier",   "33 rue Jean Moulin",        "30000", "Nîmes",            "07 37 48 59 70", "nadine.gauthier@example.fr"),
    ("Monsieur", "Éric",      "Dumont",     "2 place du Capitole",       "31000", "Toulouse",         "06 38 49 60 71", "eric.dumont@example.fr"),
    ("Madame",   "Jacqueline","Lopez",      "19 rue du Théâtre",         "64200", "Biarritz",         "07 39 50 61 72", "jacqueline.lopez@example.fr"),
    ("Monsieur", "Yves",      "Fontaine",   "7 avenue Gambetta",         "10000", "Troyes",           "06 40 51 62 73", "yves.fontaine@example.fr"),
    ("Madame",   "Béatrice",  "Chevalier",  "24 rue Montaigne",          "24000", "Périgueux",        "07 41 52 63 74", "beatrice.chevalier@example.fr"),
    ("Monsieur", "Sébastien", "Robin",      "10 rue Georges Clemenceau", "22000", "Saint-Brieuc",     "06 42 53 64 75", "sebastien.robin@example.fr"),
]


def create_db(reset=False):
    """Crée la base et insère les clients (si vide ou reset)."""
    if reset and DB_PATH.exists():
        DB_PATH.unlink()
        print(f"Base supprimée : {DB_PATH}")

    conn = sqlite3.connect(DB_PATH)
    conn.executescript(SCHEMA)

    count = conn.execute("SELECT COUNT(*) FROM clients").fetchone()[0]
    if count > 0:
        print(f"Base déjà peuplée ({count} clients). Utilisez --reset pour réinitialiser.")
        conn.close()
        return

    conn.executemany(
        "INSERT INTO clients (civilite, prenom, nom, adresse, code_postal, ville, telephone, email) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        CLIENTS,
    )
    conn.commit()

    total = conn.execute("SELECT COUNT(*) FROM clients").fetchone()[0]
    print(f"Base créée : {DB_PATH}")
    print(f"Clients insérés : {total}")
    conn.close()


if __name__ == "__main__":
    reset = "--reset" in sys.argv
    create_db(reset=reset)
