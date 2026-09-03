# CPLEX reference-day corpus

This directory is a repository-local, immutable correctness corpus copied from
the user-supplied vSPD archive. Each sampled day contains the original input
GDX and the complete set of CPLEX-produced CSV results available for that day.

The six dates were selected reproducibly: eligible dates were scored with
SHA-256 over `pyspd-cplex-reference-sample-v1|year|YYYYMMDD|input_filename`, then
the three lowest scores in each year were retained. For 2019, only dates with
one unambiguous final-pricing GDX were eligible. The lowest-scoring day in each
year is the designated two-path execution day.

`manifest.json` records the selection scores, byte sizes, input hashes, result
tree hashes, and expected result-file counts. A result tree hash is SHA-256 over
the concatenation, in bytewise relative-path order, of each relative filename,
a NUL byte, its file SHA-256, and a newline.

The 2019 files use the legacy vSPD final-pricing schema and must be requested as
`vspd-v3-final-pricing`. The 2023 files use `vspd-v5.0.6`. PySPD deliberately
does not infer these schemas from filenames or dates.

The copied data are reference evidence, not generated test output. Do not
rewrite the files when regenerating comparisons.
