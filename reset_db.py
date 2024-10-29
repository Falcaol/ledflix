from database import Base, engine

def reset_database():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)

if __name__ == "__main__":
    reset_database()
    print("Base de données réinitialisée avec succès!") 