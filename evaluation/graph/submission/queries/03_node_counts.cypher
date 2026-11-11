// Whole database, including any presentation and fixture metadata.
// A multi-label node contributes once to each of its labels.
MATCH (node)
UNWIND labels(node) AS label
RETURN label, count(*) AS nodes
ORDER BY nodes DESC, label;
