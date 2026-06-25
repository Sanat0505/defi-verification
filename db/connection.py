import os
from neo4j import GraphDatabase
from dotenv import load_dotenv

load_dotenv()

_driver = GraphDatabase.driver(
    os.getenv("NEO4J_URI"),
    auth=(os.getenv("NEO4J_USER"), os.getenv("NEO4J_PASSWORD"))
)

def get_session():
    return _driver.session()

def test_connection():
    with get_session() as s:
        r = s.run("RETURN 'Connected to Neo4j!' AS msg")
        print(r.single()["msg"])

if __name__ == "__main__":
    test_connection()