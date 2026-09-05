# Extending PySPD

Extensions must be named, class-based, versioned, and independently testable.
Do not hide a policy change behind a date check in a shared equation rule.

## Add a new model component

1. Define immutable typed input data and invariants.
2. Add a preprocessing step that maps source symbols explicitly.
3. Implement a `ModelComponent` with declared `requires` and `provides`.
4. Register every owned Pyomo object in `ModelArtifacts`.
5. Add the component class to a new or compatible `Formulation`.
6. Add canonical matrix and independent residual tests.
7. Extend pricing/results/reports only where the new algebra requires it.
8. Record an ADR and probity red/green evidence.

Conceptual skeleton:

```python
from collections.abc import Mapping
from typing import Any

from pyspd.architecture import BuildContext, ModelComponent


class StorageBalanceComponent(ModelComponent):
    name = "storage_balance"
    requires = frozenset({"case_datetime", "generation"})
    provides = frozenset({"storage_state", "storage_balance"})

    def build(self, context: BuildContext) -> Mapping[str, Any]:
        # Build owned Pyomo variables/constraints from immutable typed data.
        return {
            "storage_state": storage_state,
            "storage_balance": storage_balance,
        }
```

This example is illustrative: storage is not implemented, and a real component
must define time ordering, initial/terminal state, efficiency, power/energy
bounds, reserve participation, objective terms, and validation.

## Add a formulation version

Use a new `formulation_id` when algebra, domains, price policy, or compatibility
changes materially. Provide:

- compatibility policy and effective date;
- source profile/schema mapping;
- component graph and structural signature;
- solve and pricing policies;
- result/report profile registration;
- independent validator; and
- baseline and edge-case evidence.

Register the formulation at the application composition root only after its
public contract and fail-closed compatibility tests exist.

## Add a scenario family

For a new raw-input override:

1. add an `OverrideFamily` enum member;
2. define exact target dimensions and source symbol/component;
3. validate scope, units, finite values and domain membership;
4. return immutable changed symbols plus before/after audit entries;
5. test all precedence scopes and zero values; and
6. include scenario definition and output hashes in evidence.

For complex transformations such as PV profiles, storage fleets, topology
changes, or scarcity regimes, create a dedicated scenario/data/overlay class
instead of overloading a scalar instruction.

## Add a solver backend

Implement the solver interface without implicit fallback. Expose a distinct
profile name, dependency group, options and environment fingerprint. Test:

- availability and failure behavior;
- solution-status translation;
- value loading;
- discrete/SOS fixing;
- objective and feasibility residues;
- price finite differences; and
- corpus parity against the retained profile.

Keep primary MIP selection separate from fixed-RMIP pricing. Replacing only one
stage is a new explicit profile.

## Add report fields

Add fields to the formulation's deterministic `ReportDefinition`, populate them
without mutating solver state, and update the report crosswalk. Tests must cover
field order, units, row identities, serialization, hash round trip, and mapping
to any Authority reference column.

Schema changes are externally visible. Version the report contract if downstream
consumers cannot safely accept the addition.
