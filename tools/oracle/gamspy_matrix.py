"""Licence-compliant GAMSPy replay of a GAMS Convert fixed-LP matrix."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class FixedMatrixSolve:
    """Solver result with marginals keyed by the original GAMS equation text."""

    solver: str
    status: str
    objective: float
    equation_marginals: dict[str, float]
    primary_objective: float | None = None
    discrete_state: dict[str, dict[str, float]] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "solver": self.solver,
            "status": self.status,
            "objective": self.objective,
            "primary_objective": self.primary_objective,
            "discrete_state": self.discrete_state,
            "equation_marginals": self.equation_marginals,
        }


class GamspyFixedMatrixOracle:
    """Rebuild and solve the linear model encoded by GAMS Convert ``DumpGDX``.

    A GAMSPy licence cannot execute the original GAMS source.  It can, however,
    solve a model constructed with GAMSPy.  This adapter reconstructs the
    exported fixed-RMIP Jacobian as a continuous LP while preserving the
    original equation index, so CPLEX marginals can be mapped back to vSPD.
    """

    def solve(
        self,
        matrix: Path,
        *,
        solver: str = "CPLEX",
        equation_contains: tuple[str, ...] = (),
        solver_options: dict[str, Any] | None = None,
        mip_then_fixed: bool = False,
    ) -> FixedMatrixSolve:
        import gamspy as gp
        from gamspy.math import map_value

        with gp.Container(load_from=str(matrix)) as container:
            # Container lookup is intentionally dynamic; the concrete symbol
            # types are guaranteed by the GAMS Convert DumpGDX contract.
            i: Any = container["i"]
            j: Any = container["j"]
            jobj: Any = container["jobj"]
            objcoef: Any = container["objcoef"]
            source_equation: Any = container["e"]
            source_variable: Any = container["x"]
            jacobian: Any = container["A"]
            binary_index: Any = container["jb"]
            integer_index: Any = container["ji"]
            semicont_index: Any = container["jsc"]
            semiint_index: Any = container["jsi"]
            sos: Any = container["s"]
            sos1_index: Any = container["js1"]
            sos2_index: Any = container["js2"]

            discrete_index = gp.Set(container, "pyspd_discrete", domain=j)
            sos_index = gp.Set(container, "pyspd_sos", domain=j)
            continuous_index = gp.Set(container, "pyspd_continuous_index", domain=j)
            discrete_index[j] = (
                binary_index[j]
                | integer_index[j]
                | semicont_index[j]
                | semiint_index[j]
            )
            sos_index[j] = gp.Sum(sos1_index[sos, j], True)
            discrete_index[sos_index] = True
            sos_index[j] = gp.Sum(sos2_index[sos, j], True)
            discrete_index[sos_index] = True
            continuous_index[j] = True
            continuous_index[discrete_index] = False

            continuous = gp.Variable(container, "pyspd_continuous", domain=j)
            continuous.records = source_variable.records
            binary = gp.Variable(
                container, "pyspd_binary", domain=j, type=gp.VariableType.BINARY
            )
            integer = gp.Variable(
                container, "pyspd_integer", domain=j, type=gp.VariableType.INTEGER
            )
            semicont = gp.Variable(
                container, "pyspd_semicont", domain=j, type=gp.VariableType.SEMICONT
            )
            semiint = gp.Variable(
                container, "pyspd_semiint", domain=j, type=gp.VariableType.SEMIINT
            )
            sos1 = gp.Variable(
                container,
                "pyspd_sos1",
                domain=[sos, j],
                type=gp.VariableType.SOS1,
            )
            sos2 = gp.Variable(
                container,
                "pyspd_sos2",
                domain=[sos, j],
                type=gp.VariableType.SOS2,
            )
            for target, index in (
                (binary, binary_index),
                (integer, integer_index),
                (semicont, semicont_index),
                (semiint, semiint_index),
            ):
                target.lo[index] = continuous.lo[index]
                target.up[index] = continuous.up[index]
                target.prior[index] = continuous.scale[index]
            for target, index in ((sos1, sos1_index), (sos2, sos2_index)):
                target.lo[index[sos, j]] = continuous.lo[j]
                target.up[index[sos, j]] = continuous.up[j]
                target.prior[index[sos, j]] = continuous.scale[j]

            nonzero = gp.Set(container, "pyspd_nonzero", domain=[i, j])
            nonzero[i, j] = jacobian[i, j]

            slack = gp.Variable(
                container,
                "pyspd_row_slack",
                domain=i,
                description="slack used to retain GAMS Convert row senses",
            )
            slack.fx[i] = 0
            slack.lo[i].where[map_value(source_equation.lo[i]) == 7] = (
                gp.SpecialValues.NEGINF
            )
            slack.up[i].where[map_value(source_equation.up[i]) == 6] = (
                gp.SpecialValues.POSINF
            )

            rhs = gp.Parameter(container, "pyspd_rhs", domain=i)
            objective_coefficient = gp.Parameter(
                container, "pyspd_objective_coefficient", domain=i
            )
            objective_coefficient[i] = gp.Sum(jobj, jacobian[i, jobj])
            jacobian[i, jobj] = 0
            rhs[i].where[map_value(source_equation.up[i]) == 0] = (
                source_equation.up[i]
            )
            rhs[i].where[map_value(source_equation.lo[i]) == 0] = (
                source_equation.lo[i]
            )

            objective = gp.Variable(container, "pyspd_objective")
            reconstructed = gp.Equation(container, "pyspd_equation", domain=i)
            reconstructed[i] = (
                gp.Sum(
                    nonzero[i, j],
                    gp.Sum(
                        continuous_index[j], jacobian[i, j] * continuous[j]
                    )
                    + gp.Sum(binary_index[j], jacobian[i, j] * binary[j])
                    + gp.Sum(integer_index[j], jacobian[i, j] * integer[j])
                    + gp.Sum(semicont_index[j], jacobian[i, j] * semicont[j])
                    + gp.Sum(semiint_index[j], jacobian[i, j] * semiint[j])
                    + gp.Sum(sos1_index[sos, j], jacobian[i, j] * sos1[sos, j])
                    + gp.Sum(sos2_index[sos, j], jacobian[i, j] * sos2[sos, j]),
                )
                + objective * objective_coefficient[i]
                == rhs[i] + slack[i]
            )

            sense = (
                gp.Sense.MAX if float(objcoef.toValue()) < 0 else gp.Sense.MIN
            )
            solve_options = gp.Options(
                equation_listing_limit=0,
                variable_listing_limit=0,
                report_solution=0,
            )
            primary_objective: float | None = None
            discrete_state: dict[str, dict[str, float]] | None = None
            if mip_then_fixed:
                primary = gp.Model(
                    container,
                    "pyspd_matrix_mip",
                    equations=[reconstructed],
                    problem=gp.Problem.MIP,
                    sense=sense,
                    objective=objective,
                )
                primary.solve(
                    solver=solver,
                    options=solve_options,
                    solver_options=solver_options or {},
                )
                _require_optimal(primary.status, "primary MIP")
                primary_objective = float(primary.objective_value)
                discrete_state = {
                    "binary": _variable_levels(
                        j.records, binary.records, include_zero=True
                    ),
                    "integer": _variable_levels(
                        j.records, integer.records, include_zero=True
                    ),
                    "sos1_active": _variable_levels(
                        j.records, sos1.records, include_zero=False
                    ),
                    "sos2_active": _variable_levels(
                        j.records, sos2.records, include_zero=False
                    ),
                }
                binary.fx[binary_index] = binary.l[binary_index]
                integer.fx[integer_index] = integer.l[integer_index]
                semicont.fx[semicont_index].where[
                    gp.math.abs(semicont.l[semicont_index]) <= 1e-7
                ] = 0
                semiint.fx[semiint_index] = semiint.l[semiint_index]
                sos1.fx[sos1_index[sos, j]].where[
                    gp.math.abs(sos1.l[sos, j]) <= 1e-7
                ] = 0
                sos2.fx[sos2_index[sos, j]].where[
                    gp.math.abs(sos2.l[sos, j]) <= 1e-7
                ] = 0

            model = gp.Model(
                container,
                "pyspd_fixed_matrix",
                equations=[reconstructed],
                problem=gp.Problem.RMIP,
                sense=sense,
                objective=objective,
            )
            model.solve(
                solver=solver,
                options=solve_options,
                solver_options=solver_options or {},
            )
            _require_optimal(model.status, "fixed RMIP")
            marginals = _equation_marginals(
                i.records,
                reconstructed.records,
                equation_contains=equation_contains,
            )
            if equation_contains and not marginals:
                raise ValueError(
                    "no equation descriptions matched: "
                    + ", ".join(equation_contains)
                )
            return FixedMatrixSolve(
                solver=solver.upper(),
                status=str(model.status),
                objective=float(model.objective_value),
                equation_marginals=marginals,
                primary_objective=primary_objective,
                discrete_state=discrete_state,
            )


def _equation_marginals(
    index_records: Any,
    solution_records: Any,
    *,
    equation_contains: tuple[str, ...] = (),
) -> dict[str, float]:
    """Map Convert row identifiers to stable original equation descriptions."""

    descriptions = dict(
        zip(
            index_records.iloc[:, 0].astype(str),
            index_records["element_text"].astype(str),
            strict=True,
        )
    )
    selected: dict[str, float] = {}
    for _, record in solution_records.iterrows():
        description = descriptions[str(record.iloc[0])]
        if equation_contains and not any(
            token in description for token in equation_contains
        ):
            continue
        selected[description] = float(record["marginal"])
    return dict(sorted(selected.items()))


def _variable_levels(
    index_records: Any,
    solution_records: Any,
    *,
    include_zero: bool,
) -> dict[str, float]:
    """Map Convert column identifiers to original variable descriptions."""

    if solution_records is None:
        return {}
    descriptions = dict(
        zip(
            index_records.iloc[:, 0].astype(str),
            index_records["element_text"].astype(str),
            strict=True,
        )
    )
    selected: dict[str, float] = {}
    for _, record in solution_records.iterrows():
        level = float(record["level"])
        if not include_zero and abs(level) <= 1e-7:
            continue
        selected[descriptions[str(record["j"])]] = level
    return dict(sorted(selected.items()))


def _require_optimal(status: Any, stage: str) -> None:
    if str(status) != "ModelStatus.OptimalGlobal":
        raise RuntimeError(f"{stage} did not return an optimal solution: {status}")
