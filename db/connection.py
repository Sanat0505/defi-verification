import os
from neo4j import GraphDatabase
from dotenv import load_dotenv

load_dotenv()

_driver = None


def get_driver():
    """Create the Neo4j driver lazily so imports and unit tests need no database."""
    global _driver
    if _driver is None:
        uri = os.getenv("NEO4J_URI")
        user = os.getenv("NEO4J_USER")
        password = os.getenv("NEO4J_PASSWORD")
        missing = [name for name, value in (
            ("NEO4J_URI", uri), ("NEO4J_USER", user), ("NEO4J_PASSWORD", password)
        ) if not value]
        if missing:
            raise RuntimeError(f"Missing Neo4j configuration: {', '.join(missing)}")
        _driver = GraphDatabase.driver(uri, auth=(user, password))
    return _driver

def get_session():
    return get_driver().session()


def close_driver():
    global _driver
    if _driver is not None:
        _driver.close()
        _driver = None

def test_connection():
    with get_session() as s:
        r = s.run("RETURN 'Connected to Neo4j!' AS msg")
        print(r.single()["msg"])

if __name__ == "__main__":
    test_connection()
