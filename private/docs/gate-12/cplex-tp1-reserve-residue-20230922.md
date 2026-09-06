# 2023-09-22 TP1 reserve-price residue

## Outcome

The two remaining TP1 SI reserve-price differences are **not certified**. The
historical archive reports FIR/SIR prices of `0.07398/0.08696` NZD/MWh for the
00:20 and 00:25 cases. SCIP → HiGHS, current CPLEX MIP → fixed RMIP, and
CPLEX's native `solvefinal` continuation all return
`0.071439996091/0.089316334332` on the captured vSPD matrix.

This distinction matters: the archive remains the requested gold record, but
its values must not be copied into PySPD without a reproducible mathematical or
historical execution rule. The comparison therefore continues to fail closed
on these two scalar publications.

## Excluded explanations

The diagnosis excluded the following candidate explanations:

1. **A one-dimensional dual interval.** At a 0.001 MW perturbation, both the
   left and right objective derivatives reproduce the current FIR and SIR
   duals. The archived values are outside those derivatives.
2. **A different reserve-zone binary.** All nine SI FIR/SIR combinations of
   `NR`, `RP`, and `RZ` were solved. Every optimal combination returns the
   current pair; non-optimal combinations lose between 4.29 and 43.03 NZD.
3. **A CPLEX basis or algorithm convention.** Primal simplex, dual simplex,
   barrier, scaling on/off, and dual-optimality tolerances from `1e-9` through
   `1e-4` do not reproduce the archived FIR value.
4. **The archived HVDC flow as an alternate endpoint.** Imposing the archived
   flow on the current matrix returns `0.01/0.01`, not the archived reserve
   prices, and loses 0.04485 NZD and 0.05171 NZD of net benefit respectively.
5. **vSPD daily-mode load reconstruction.** The v5.0.2 `dailymode=0` run detects
   first-pass loss differences, applies the source `SPDLoadCalcLosses` override,
   and converges to the same final objective and prices as the current replay.

The surviving explanations require evidence not present in the archive: a
different historical final matrix, an older CPLEX/GAMS numerical implementation,
or a different executable configuration. The evidence is hash-bound in
[`cplex-tp1-reserve-residue-20230922.json`](cplex-tp1-reserve-residue-20230922.json).

## Next bounded work

TP24 is independent of this residue and has a provable equivalence class. The
archive and PySPD each clear 55 MW from the three TUI1101 offers. They differ
only by reallocating 3.486 MW between the `PRI0` and `TUI0` second blocks, both
priced at 210.07 NZD/MWh, across an unconstrained lossless transformer star.
That difference can be handled with a source-backed alternate-allocation
certificate without changing the dispatch model or weakening scalar tolerances.
