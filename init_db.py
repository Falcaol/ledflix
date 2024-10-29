from database import Base, engine
from dotenv import load_dotenv
import os

# Charger les variables d'environnement
load_dotenv()

def init_db():
    """Initialise la base de données"""
    Base.metadata.create_all(engine)

if __name__ == "__main__":
    init_db()
    print("Base de données initialisée!") 