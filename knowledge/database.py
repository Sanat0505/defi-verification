"""Explicit database isolation, atomic publication, and read-only catalog queries."""

from __future__ import annotations

from collections import defaultdict
import hashlib
import json
import os
import re

from db.connection import get_driver

DATABASE = "defi-knowledge-expanded"
OWNER = "defi-verification-expanded-v1"
CATALOG = "protocol-knowledge"


def database_name(value: str | None = None) -> str:
    name = value or os.getenv("KNOWLEDGE_DATABASE", DATABASE)
    # Deliberately refuse neo4j, system, thesis databases and arbitrary names.
    if not re.fullmatch(r"defi-knowledge-[a-z0-9-]{1,40}", name):
        raise ValueError("Knowledge database name must start with 'defi-knowledge-' and contain only lowercase letters, digits and hyphens")
    return name


def check_owner(tx, allow_empty=False):
    if allow_empty and not tx.run("MATCH (n) RETURN n LIMIT 1").peek():
        return
    roots = list(tx.run("MATCH (c:KnowledgeCatalog) RETURN c.name AS name, c.owner AS owner"))
    if len(roots) == 1 and roots[0]["name"] == CATALOG and roots[0]["owner"] == OWNER:
        return
    raise ValueError("Refusing to use an existing database without the expanded-knowledge ownership marker")


def provision(driver=None, database=None):
    driver = driver or get_driver()
    name = database_name(database)
    with driver.session(database="system") as session:
        dbs = list(session.run("SHOW DATABASES YIELD name, default RETURN name, default"))
        if any(row["name"] == name and row["default"] for row in dbs):
            raise ValueError("Refusing to use the default database for expanded knowledge")
        if not any(row["name"] == name for row in dbs):
            session.run(f"CREATE DATABASE `{name}` IF NOT EXISTS WAIT 30 SECONDS").consume()
    with driver.session(database=name) as session:
        session.execute_read(lambda tx: check_owner(tx, allow_empty=True))
        # Schema is only changed after ownership/emptiness was checked.
        for label in ("KnowledgeCatalog", "KnowledgeSnapshot", "KnowledgeEntity"):
            field = "name" if label == "KnowledgeCatalog" else "key"
            session.run(f"CREATE CONSTRAINT {label.lower()}_key IF NOT EXISTS FOR (n:{label}) REQUIRE n.{field} IS UNIQUE").consume()

        def claim(tx):
            check_owner(tx, allow_empty=True)
            tx.run("MERGE (c:KnowledgeCatalog {name:$name}) SET c.owner=$owner", name=CATALOG, owner=OWNER).consume()
        session.execute_write(claim)
    return name


def _publish(tx, graph, snapshot_id):
    from knowledge.model import LABELS, RELATIONS
    from knowledge.sources import canonical

    check_owner(tx)
    existing = tx.run("MATCH (s:KnowledgeSnapshot {key:$id}) RETURN s.complete AS complete", id=snapshot_id).single()
    if existing and not existing["complete"]:
        raise ValueError("Incomplete snapshot with matching identity")
    if not existing:
        tx.run("CREATE (s:KnowledgeSnapshot {key:$id, complete:false, created_at:datetime(), schema_version:$schema})",
               id=snapshot_id, schema=graph.document()["schema_version"]).consume()
        by_label, by_type = defaultdict(list), defaultdict(list)
        for node in graph.nodes.values():
            if node["label"] not in LABELS:
                raise ValueError("Invalid label")
            by_label[node["label"]].append({"key": snapshot_id + ":" + node["key"], "logical_key": node["key"], "props": node["properties"]})
        for label, rows in by_label.items():
            tx.run(f"""MATCH (s:KnowledgeSnapshot {{key:$id}})
                UNWIND $rows AS row
                CREATE (n:KnowledgeEntity:{label} {{key:row.key}})
                SET n += row.props, n.snapshot_id=$id, n.logical_key=row.logical_key
                CREATE (s)-[:CONTAINS]->(n)""", id=snapshot_id, rows=rows).consume()
        for edge in graph.edges.values():
            if edge["type"] not in RELATIONS:
                raise ValueError("Invalid relationship type")
            by_type[edge["type"]].append({"start": snapshot_id + ":" + edge["start"], "end": snapshot_id + ":" + edge["end"], "props": edge["properties"]})
        for relation, rows in by_type.items():
            tx.run(f"""UNWIND $rows AS row
                MATCH (a:KnowledgeEntity {{key:row.start}}), (b:KnowledgeEntity {{key:row.end}})
                CREATE (a)-[r:{relation}]->(b) SET r += row.props""", rows=rows).consume()
        count = tx.run("MATCH (:KnowledgeSnapshot {key:$id})-[:CONTAINS]->(n) RETURN count(n) AS n", id=snapshot_id).single()["n"]
        edge_count = tx.run("MATCH (a:KnowledgeEntity {snapshot_id:$id})-[r]->(:KnowledgeEntity {snapshot_id:$id}) RETURN count(r) AS n", id=snapshot_id).single()["n"]
        if count != len(graph.nodes) or edge_count != len(graph.edges):
            raise ValueError("Imported graph counts differ; transaction will roll back")
        tx.run("MATCH (s:KnowledgeSnapshot {key:$id}) SET s.complete=true, s.report_json=$report",
               id=snapshot_id, report=canonical(graph.report())).consume()
    # Only this catalog pointer is replaced, inside the same transaction as the import.
    tx.run("""MATCH (c:KnowledgeCatalog {name:$name}), (s:KnowledgeSnapshot {key:$id, complete:true})
        OPTIONAL MATCH (c)-[old:ACTIVE]->() DELETE old
        MERGE (c)-[:ACTIVE]->(s)""", name=CATALOG, id=snapshot_id).consume()
    return {"snapshot_id": snapshot_id, "already_present": bool(existing)}


def publish(graph, driver=None, database=None):
    graph.validate()
    snapshot_id = graph.snapshot_id
    driver = driver or get_driver()
    name = database_name(database)
    with driver.session(database=name) as session:
        result = session.execute_write(_publish, graph, snapshot_id)
    return {"database": name, **result}


def summary(driver=None, database=None):
    driver = driver or get_driver()
    name = database_name(database)
    with driver.session(database=name, default_access_mode="READ") as session:
        def read(tx):
            check_owner(tx)
            row = tx.run("""MATCH (:KnowledgeCatalog {name:$name})-[:ACTIVE]->(s:KnowledgeSnapshot {complete:true})
                RETURN s.report_json AS report""", name=CATALOG).single()
            if not row:
                raise ValueError("No completed knowledge snapshot has been published")
            return {"database": name, **json.loads(row["report"])}
        return session.execute_read(read)


def entries(kind, *, module=None, name=None, limit=100, offset=0, driver=None, database=None):
    if kind not in {"Operation", "Function", "Contract", "CoverageGap"}:
        raise ValueError("Unsupported catalog entry type")
    if not 1 <= limit <= 200 or not 0 <= offset <= 100000:
        raise ValueError("Invalid pagination")
    driver = driver or get_driver()
    with driver.session(database=database_name(database), default_access_mode="READ") as session:
        def read(tx):
            check_owner(tx)
            rows = tx.run(f"""MATCH (:KnowledgeCatalog {{name:$catalog}})-[:ACTIVE]->(s:KnowledgeSnapshot {{complete:true}})
                MATCH (s)-[:CONTAINS]->(n:{kind})
                WHERE ($module IS NULL OR n.module=$module) AND
                      ($name IS NULL OR toLower(coalesce(n.action,n.name,n.role,n.code,'')) CONTAINS toLower($name))
                OPTIONAL MATCH (n)-[:EVIDENCED_BY]->(source:Source)
                RETURN properties(n) AS item, collect(source.url) AS sources
                ORDER BY item.logical_key SKIP $offset LIMIT $limit""",
                catalog=CATALOG, module=module, name=name, limit=limit, offset=offset)
            return [{"item": {k: v for k, v in row["item"].items() if k != "key"}, "sources": row["sources"]} for row in rows]
        return session.execute_read(read)


def fingerprint(database="neo4j", driver=None):
    """Read-only content fingerprint for checking preservation of existing graphs."""
    driver = driver or get_driver()
    with driver.session(database=database, default_access_mode="READ") as session:
        def read(tx):
            hasher = hashlib.sha256()
            counts = {}
            for kind, statement in (
                ("nodes", "MATCH (n) RETURN elementId(n) AS id, labels(n) AS labels, properties(n) AS properties ORDER BY id"),
                ("relationships", "MATCH (a)-[r]->(b) RETURN elementId(r) AS id, elementId(a) AS start, elementId(b) AS end, type(r) AS type, properties(r) AS properties ORDER BY id"),
            ):
                count = 0
                for row in tx.run(statement):
                    data = dict(row)
                    if "labels" in data:
                        data["labels"] = sorted(data["labels"])
                    hasher.update(json.dumps(data, sort_keys=True, default=str, separators=(",", ":")).encode())
                    hasher.update(b"\n")
                    count += 1
                counts[kind] = count
            return {"database": database, "sha256": hasher.hexdigest(), **counts}
        return session.execute_read(read)
