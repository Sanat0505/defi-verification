// One-time migration for existing databases; safe to rerun.
// Renames view metadata only. Nodes and INCLUDES relationships are preserved.
// If a target key already exists, skip that rename instead of duplicating it.
UNWIND [
  {oldKey:'professor-small-verification', newKey:'small-verification'},
  {oldKey:'professor-large-graph', newKey:'large-graph'}
] AS rename
MATCH (view:GraphView {key:rename.oldKey})
WHERE NOT EXISTS { MATCH (:GraphView {key:rename.newKey}) }
SET view.key = rename.newKey
RETURN rename.oldKey AS previous_key, view.key AS current_key;
