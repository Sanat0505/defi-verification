// Whole database; INCLUDES and any fixture edges are counted explicitly.
MATCH ()-[relationship]->()
RETURN type(relationship) AS relationship_type, count(*) AS relationships
ORDER BY relationships DESC, relationship_type;
