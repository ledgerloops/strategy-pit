# Coordinated exact reference

This package reports a coordinated Bellman–Ford research reference measured on
20 October 2026. It uses supplied membership, a fixed epoch coordinator,
path-disclosing messages, reliable delivery and serialized frozen epochs. It does
not establish coordinator-free, neighbour-private or concurrent product operation.

[Report](report.html) · [Chart](exact-clearing-arrivals.png) ·
[Reproduction](REPRODUCE.txt) · [Independent audit](independent-audit.json)

The chart compares different stopping rules: the reference seeks a certificate
within a 2,000,000-message safety ceiling; the debt-first control receives 1,024
messages per original trustline total. It is not a matched-budget superiority test.
Broad completion matches the independent hard-bound optimum; narrow completion
only excludes currently admissible improving unit cycles.

Presentation-only correction: earlier headings called this an exact node-local
algorithm. Headings, legends and explanatory text now say **Coordinated exact
reference**. The raw `exact` method key is retained. Actor source, benchmark
runner, plan, workload, prospective freeze, results, audit and numeric comparison
tables are unchanged. The report renderer and generated chart/report changed;
`SOURCE-MANIFEST.json` records the original renderer hash and updated presentation
source hash. `SHA256SUMS.txt` covers the revised files. The ZIP contains the revised
PNG under its original filename.
