#!/usr/bin/env python3
from __future__ import annotations

import json
import math
import sys
from collections import deque
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml
from jsonschema import Draft202012Validator, FormatChecker


ROOT = Path(__file__).resolve().parents[1]
SCHEMA_DIR = ROOT / "schemas"
PASS_DIR = ROOT / "examples" / "pass"
FAIL_DIR = ROOT / "examples" / "fail"


SCHEMA_FILES = {
    "origin_record":
        SCHEMA_DIR / "origin-record.schema.json",

    "derivative_record":
        SCHEMA_DIR / "derivative-record.schema.json",

    "trace_record":
        SCHEMA_DIR / "trace-record.schema.json",

    "trace_chain_record":
        SCHEMA_DIR / "trace-chain-record.schema.json",

    "evidence_assessment_record":
        SCHEMA_DIR / "evidence-assessment-record.schema.json",

    "contribution_assessment_record":
        SCHEMA_DIR / "contribution-assessment-record.schema.json",

    "audit_record":
        SCHEMA_DIR / "audit-record.schema.json",

    "royalty_record":
        SCHEMA_DIR / "royalty-record.schema.json",

    "state_transition_record":
        SCHEMA_DIR / "state-transition-record.schema.json",

    "value_cycle_record":
        SCHEMA_DIR / "value-cycle-record.schema.json",
}


ID_FIELDS = {
    "origin_record": "origin_id",
    "derivative_record": "derivative_id",
    "trace_record": "trace_id",
    "trace_chain_record": "trace_chain_id",
    "evidence_assessment_record":
        "evidence_assessment_id",
    "contribution_assessment_record":
        "contribution_assessment_id",
    "audit_record": "audit_id",
    "royalty_record": "royalty_id",
    "state_transition_record": "transition_id",
    "value_cycle_record": "cycle_id",
}


LEGAL_TRANSITIONS = {
    (
        "origin_registered",
        "derivative_created",
    ),
    (
        "derivative_created",
        "trace_recorded",
    ),
    (
        "trace_recorded",
        "audit_pending",
    ),
    (
        "audit_pending",
        "audit_provisional",
    ),
    (
        "audit_pending",
        "audit_verified",
    ),
    (
        "audit_pending",
        "disputed",
    ),
    (
        "audit_provisional",
        "audit_pending",
    ),
    (
        "audit_provisional",
        "audit_verified",
    ),
    (
        "disputed",
        "audit_pending",
    ),
    (
        "audit_verified",
        "royalty_calculated",
    ),
    (
        "royalty_calculated",
        "settlement_pending",
    ),
    (
        "settlement_pending",
        "settled",
    ),
    (
        "settlement_pending",
        "disputed",
    ),
    (
        "disputed",
        "settlement_pending",
    ),
}


COEFFICIENT_FIELDS = (
    "reference_depth",
    "transformation_dependency",
    "reasoning_influence",
    "decision_influence",
    "outcome_influence",
)


STANDARD_AUDIT_PROFILE = (
    "cvcp-standard-audit-v1"
)

EPSILON = 1e-9


class ValidationFailure(Exception):
    pass


def load_document(
    path: Path,
) -> dict[str, Any]:

    try:
        text = path.read_text(
            encoding="utf-8",
        )

    except OSError as exc:
        raise ValidationFailure(
            f"cannot read {path}: {exc}"
        ) from exc

    try:
        if path.suffix.lower() == ".json":
            data = json.loads(text)

        else:
            data = yaml.safe_load(text)

    except (
        json.JSONDecodeError,
        yaml.YAMLError,
    ) as exc:

        raise ValidationFailure(
            f"cannot parse {path}: {exc}"
        ) from exc

    if not isinstance(data, dict):
        raise ValidationFailure(
            f"{path}: top-level document "
            "must be an object"
        )

    return data


def expand_fixture(
    document: dict[str, Any],
) -> list[dict[str, Any]]:

    if (
        document.get("fixture_type")
        != "semantic_scenario"
    ):
        return [document]

    records = document.get("records")

    if (
        not isinstance(records, list)
        or not records
    ):
        raise ValidationFailure(
            "semantic_scenario requires "
            "a non-empty records array"
        )

    if not all(
        isinstance(record, dict)
        for record in records
    ):
        raise ValidationFailure(
            "every semantic_scenario record "
            "must be an object"
        )

    return records


def example_files(
    directory: Path,
) -> list[Path]:

    paths: list[Path] = []

    for suffix in (
        "*.yaml",
        "*.yml",
        "*.json",
    ):
        paths.extend(
            directory.glob(suffix)
        )

    return sorted(
        set(paths),
        key=lambda path: path.name,
    )


def load_schemas(
) -> dict[
    str,
    Draft202012Validator,
]:

    validators: dict[
        str,
        Draft202012Validator,
    ] = {}

    for (
        record_type,
        path,
    ) in SCHEMA_FILES.items():

        schema = load_document(path)

        Draft202012Validator.check_schema(
            schema
        )

        validators[
            record_type
        ] = Draft202012Validator(
            schema,
            format_checker=FormatChecker(),
        )

    return validators


def schema_errors(
    record: dict[str, Any],
    validators: dict[
        str,
        Draft202012Validator,
    ],
) -> list[str]:

    record_type = record.get(
        "record_type"
    )

    if record_type not in validators:
        return [
            "unknown or missing "
            f"record_type: {record_type!r}"
        ]

    errors = sorted(
        validators[
            record_type
        ].iter_errors(record),
        key=lambda error:
            str(
                list(
                    error.absolute_path
                )
            ),
    )

    result: list[str] = []

    for error in errors:

        path = "$"

        for part in error.absolute_path:

            if isinstance(part, int):
                path += f"[{part}]"

            else:
                path += f".{part}"

        result.append(
            f"{path}: {error.message}"
        )

    return result


def parse_datetime(
    value: str,
) -> datetime:

    if value.endswith("Z"):
        value = (
            value[:-1]
            + "+00:00"
        )

    return datetime.fromisoformat(
        value
    )


def close_enough(
    left: float,
    right: float,
) -> bool:

    return math.isclose(
        float(left),
        float(right),
        rel_tol=EPSILON,
        abs_tol=EPSILON,
    )


def build_index(
    records: list[
        dict[str, Any]
    ],
) -> tuple[
    dict[
        str,
        dict[
            str,
            dict[str, Any],
        ],
    ],
    list[str],
]:

    index = {
        record_type: {}
        for record_type
        in ID_FIELDS
    }

    errors: list[str] = []

    for record in records:

        record_type = record.get(
            "record_type"
        )

        id_field = ID_FIELDS.get(
            record_type
        )

        if id_field is None:
            continue

        record_id = record.get(
            id_field
        )

        if not isinstance(
            record_id,
            str,
        ):
            continue

        if (
            record_id
            in index[record_type]
        ):
            errors.append(
                f"duplicate {id_field}: "
                f"{record_id}"
            )

            continue

        index[
            record_type
        ][
            record_id
        ] = record

    return index, errors


def trace_parents(
    trace: dict[str, Any],
) -> set[str]:

    parents = set(
        trace.get(
            "causal_parent_refs",
            [],
        )
    )

    previous = trace.get(
        "previous_trace_id"
    )

    if isinstance(
        previous,
        str,
    ):
        parents.add(previous)

    return parents


def audit_confidence(
    audit: dict[str, Any],
) -> float | None:

    profile_id = (
        audit[
            "audit_profile"
        ][
            "profile_id"
        ]
    )

    if (
        profile_id
        != STANDARD_AUDIT_PROFILE
    ):
        return None

    components = audit[
        "confidence_components"
    ]

    base = (
        float(
            components[
                "evidence_quality"
            ]
        )
        + float(
            components[
                "trace_completeness"
            ]
        )
        + float(
            components[
                "contribution_stability"
            ]
        )
        + float(
            components[
                "methodology_reliability"
            ]
        )
    ) / 4.0

    return (
        base
        * (
            1.0
            - float(
                components[
                    "conflict_penalty"
                ]
            )
        )
    )


def semantic_errors(
    records: list[
        dict[str, Any]
    ],
) -> list[str]:

    index, errors = build_index(
        records
    )

    origins = index[
        "origin_record"
    ]

    derivatives = index[
        "derivative_record"
    ]

    traces = index[
        "trace_record"
    ]

    chains = index[
        "trace_chain_record"
    ]

    evidence_assessments = index[
        "evidence_assessment_record"
    ]

    contribution_assessments = index[
        "contribution_assessment_record"
    ]

    audits = index[
        "audit_record"
    ]

    royalties = index[
        "royalty_record"
    ]

    transitions = index[
        "state_transition_record"
    ]

    cycles = index[
        "value_cycle_record"
    ]

    # ======================================================
    # Origin / Derivative
    # CVCP-01 / CVCP-07
    # ======================================================

    for (
        derivative_id,
        derivative,
    ) in derivatives.items():

        compliance = {
            item["origin_id"]: item
            for item
            in derivative.get(
                "policy_compliance",
                [],
            )
            if (
                isinstance(
                    item,
                    dict,
                )
                and isinstance(
                    item.get(
                        "origin_id"
                    ),
                    str,
                )
            )
        }

        for origin_id in derivative.get(
            "origin_refs",
            [],
        ):

            origin = origins.get(
                origin_id
            )

            if origin is None:

                errors.append(
                    f"{derivative_id}: "
                    f"unknown Origin "
                    f"{origin_id}"
                )

                continue

            policy = origin[
                "access_policy"
            ]

            if (
                policy[
                    "reference"
                ]
                == "deny"
            ):
                errors.append(
                    f"{derivative_id}: "
                    f"Origin {origin_id} "
                    "denies reference"
                )

            if (
                policy[
                    "reference"
                ]
                == "conditional"
            ):

                check = compliance.get(
                    origin_id
                )

                if (
                    check is None
                    or check.get(
                        "status"
                    )
                    != "satisfied"
                ):
                    errors.append(
                        f"{derivative_id}: "
                        f"conditional Origin "
                        f"{origin_id} "
                        "requires satisfied "
                        "policy_compliance"
                    )

    # ======================================================
    # Trace parent integrity
    # CVCP-14 / 15 / 17 / 18
    # ======================================================

    for (
        trace_id,
        trace,
    ) in traces.items():

        derivative_id = trace[
            "derivative_id"
        ]

        if (
            derivative_id
            not in derivatives
        ):
            errors.append(
                f"{trace_id}: "
                f"unknown Derivative "
                f"{derivative_id}"
            )

        for parent_id in trace_parents(
            trace
        ):

            parent = traces.get(
                parent_id
            )

            if parent is None:

                errors.append(
                    f"{trace_id}: "
                    f"unknown parent Trace "
                    f"{parent_id}"
                )

                continue

            if (
                parent[
                    "derivative_id"
                ]
                != derivative_id
            ):
                errors.append(
                    f"{trace_id}: "
                    "cross-Derivative "
                    f"parent {parent_id}"
                )

            if (
                parent["sequence"]
                >= trace["sequence"]
            ):
                errors.append(
                    f"{trace_id}: "
                    "parent precedence "
                    "violated by "
                    f"{parent_id}"
                )

            if (
                parse_datetime(
                    parent[
                        "timestamp"
                    ]
                )
                >
                parse_datetime(
                    trace[
                        "timestamp"
                    ]
                )
            ):
                errors.append(
                    f"{trace_id}: "
                    "parent timestamp "
                    "occurs after child "
                    f"{parent_id}"
                )

    # ======================================================
    # Trace Chain DAG integrity
    # CVCP-13 / 16 / 19 / 20
    # ======================================================

    for (
        chain_id,
        chain,
    ) in chains.items():

        refs = chain[
            "trace_refs"
        ]

        ref_set = set(refs)

        if (
            chain[
                "event_count"
            ]
            != len(refs)
        ):
            errors.append(
                f"{chain_id}: "
                "event_count mismatch: "
                f"{chain['event_count']} "
                f"!= {len(refs)}"
            )

        if (
            chain[
                "root_trace_id"
            ]
            not in ref_set
        ):
            errors.append(
                f"{chain_id}: "
                "root_trace_id is not "
                "in trace_refs"
            )

        if not set(
            chain[
                "terminal_trace_ids"
            ]
        ).issubset(
            ref_set
        ):
            errors.append(
                f"{chain_id}: "
                "terminal Trace outside "
                "trace_refs"
            )

        nodes: dict[
            str,
            dict[str, Any],
        ] = {}

        for trace_id in refs:

            trace = traces.get(
                trace_id
            )

            if trace is None:

                errors.append(
                    f"{chain_id}: "
                    f"unknown Trace "
                    f"{trace_id}"
                )

                continue

            nodes[
                trace_id
            ] = trace

            if (
                trace[
                    "derivative_id"
                ]
                != chain[
                    "derivative_id"
                ]
            ):
                errors.append(
                    f"{chain_id}: "
                    f"Trace {trace_id} "
                    "belongs to another "
                    "Derivative"
                )

        children = {
            trace_id: set()
            for trace_id
            in nodes
        }

        roots: list[str] = []

        for (
            trace_id,
            trace,
        ) in nodes.items():

            parents = trace_parents(
                trace
            )

            in_chain = {
                parent
                for parent in parents
                if parent in nodes
            }

            outside_chain = (
                parents
                - in_chain
            )

            if outside_chain:

                errors.append(
                    f"{chain_id}: "
                    f"Trace {trace_id} "
                    "parent(s) outside "
                    "chain: "
                    f"{sorted(outside_chain)}"
                )

            if not in_chain:
                roots.append(
                    trace_id
                )

            for parent in in_chain:
                children[
                    parent
                ].add(
                    trace_id
                )

        expected_root = chain[
            "root_trace_id"
        ]

        if (
            set(roots)
            != {expected_root}
        ):
            errors.append(
                f"{chain_id}: "
                f"roots {sorted(roots)} "
                "do not equal declared "
                f"root {expected_root}"
            )

        indegree = {
            trace_id: 0
            for trace_id
            in nodes
        }

        for child_set in (
            children.values()
        ):
            for child in child_set:
                indegree[
                    child
                ] += 1

        queue = deque(
            trace_id
            for (
                trace_id,
                degree,
            ) in indegree.items()
            if degree == 0
        )

        visited: list[str] = []

        while queue:

            current = queue.popleft()

            visited.append(
                current
            )

            for child in children[
                current
            ]:

                indegree[
                    child
                ] -= 1

                if (
                    indegree[
                        child
                    ]
                    == 0
                ):
                    queue.append(
                        child
                    )

        if (
            len(visited)
            != len(nodes)
        ):
            errors.append(
                f"{chain_id}: "
                "causal cycle detected"
            )

        if expected_root in nodes:

            reachable: set[str] = set()

            queue = deque(
                [expected_root]
            )

            while queue:

                current = queue.popleft()

                if (
                    current
                    in reachable
                ):
                    continue

                reachable.add(
                    current
                )

                queue.extend(
                    children[
                        current
                    ]
                )

            unreachable = (
                set(nodes)
                - reachable
            )

            if unreachable:
                errors.append(
                    f"{chain_id}: "
                    "orphan/unreachable "
                    "Trace(s): "
                    f"{sorted(unreachable)}"
                )

        actual_terminals = {
            trace_id
            for (
                trace_id,
                child_set,
            ) in children.items()
            if not child_set
        }

        declared_terminals = set(
            chain[
                "terminal_trace_ids"
            ]
        )

        if (
            actual_terminals
            != declared_terminals
        ):
            errors.append(
                f"{chain_id}: "
                "terminal mismatch: "
                f"actual="
                f"{sorted(actual_terminals)}, "
                f"declared="
                f"{sorted(declared_terminals)}"
            )

    # ======================================================
    # Evidence Assessment
    # CVCP-26 / 27 / 28 / 38
    # ======================================================

    for (
        assessment_id,
        assessment,
    ) in evidence_assessments.items():

        derivative_id = assessment[
            "derivative_id"
        ]

        chain_id = assessment[
            "trace_chain_ref"
        ]

        origin_id = assessment[
            "origin_id"
        ]

        derivative = derivatives.get(
            derivative_id
        )

        if derivative is None:
            errors.append(
                f"{assessment_id}: "
                f"unknown Derivative "
                f"{derivative_id}"
            )

        chain = chains.get(
            chain_id
        )

        if chain is None:

            errors.append(
                f"{assessment_id}: "
                f"unknown Trace Chain "
                f"{chain_id}"
            )

            chain_trace_refs: set[
                str
            ] = set()

        else:

            chain_trace_refs = set(
                chain[
                    "trace_refs"
                ]
            )

            if (
                chain[
                    "derivative_id"
                ]
                != derivative_id
            ):
                errors.append(
                    f"{assessment_id}: "
                    "Trace Chain "
                    "Derivative mismatch"
                )

        if (
            derivative is not None
            and origin_id
            not in set(
                derivative[
                    "origin_refs"
                ]
            )
        ):
            errors.append(
                f"{assessment_id}: "
                "Evidence Origin "
                f"{origin_id} "
                "is not declared by "
                f"Derivative "
                f"{derivative_id}"
            )

        seen_items: set[
            tuple[str, str]
        ] = set()

        for item in assessment[
            "evidence_items"
        ]:

            trace_id = item[
                "trace_id"
            ]

            key = (
                trace_id,
                item[
                    "evidence_type"
                ],
            )

            if key in seen_items:
                errors.append(
                    f"{assessment_id}: "
                    "duplicate evidence "
                    "item "
                    f"{trace_id}/"
                    f"{item['evidence_type']}"
                )

            seen_items.add(key)

            trace = traces.get(
                trace_id
            )

            if trace is None:

                errors.append(
                    f"{assessment_id}: "
                    "unknown Evidence "
                    f"Trace {trace_id}"
                )

                continue

            if (
                trace_id
                not in chain_trace_refs
            ):
                errors.append(
                    f"{assessment_id}: "
                    "Evidence Trace "
                    f"{trace_id} "
                    "is not part of "
                    f"Trace Chain "
                    f"{chain_id}"
                )

            if (
                trace[
                    "derivative_id"
                ]
                != derivative_id
            ):
                errors.append(
                    f"{assessment_id}: "
                    "Evidence Trace "
                    f"{trace_id} "
                    "belongs to another "
                    "Derivative"
                )

    # ======================================================
    # Contribution Assessment
    # CVCP-26 / 28 / 30 / 31 / 32 / 33 / 39
    # ======================================================

    for (
        assessment_id,
        assessment,
    ) in contribution_assessments.items():

        derivative_id = assessment[
            "derivative_id"
        ]

        chain_id = assessment[
            "trace_chain_ref"
        ]

        derivative = derivatives.get(
            derivative_id
        )

        if derivative is None:
            errors.append(
                f"{assessment_id}: "
                f"unknown Derivative "
                f"{derivative_id}"
            )

        chain = chains.get(
            chain_id
        )

        if chain is None:

            errors.append(
                f"{assessment_id}: "
                f"unknown Trace Chain "
                f"{chain_id}"
            )

        elif (
            chain[
                "derivative_id"
            ]
            != derivative_id
        ):
            errors.append(
                f"{assessment_id}: "
                "Trace Chain "
                "Derivative mismatch"
            )

        declared_evidence_refs = set(
            assessment[
                "evidence_assessment_refs"
            ]
        )

        for evidence_ref in (
            declared_evidence_refs
        ):

            evidence = (
                evidence_assessments.get(
                    evidence_ref
                )
            )

            if evidence is None:

                errors.append(
                    f"{assessment_id}: "
                    "unknown Evidence "
                    "Assessment "
                    f"{evidence_ref}"
                )

                continue

            if (
                evidence[
                    "derivative_id"
                ]
                != derivative_id
            ):
                errors.append(
                    f"{assessment_id}: "
                    "Evidence Assessment "
                    f"{evidence_ref} "
                    "Derivative mismatch"
                )

            if (
                evidence[
                    "trace_chain_ref"
                ]
                != chain_id
            ):
                errors.append(
                    f"{assessment_id}: "
                    "Evidence Assessment "
                    f"{evidence_ref} "
                    "Trace Chain mismatch"
                )

        methodology = assessment[
            "methodology"
        ]

        coefficients = methodology[
            "coefficients"
        ]

        coefficient_sum = sum(
            float(
                coefficients[
                    field
                ]
            )
            for field
            in COEFFICIENT_FIELDS
        )

        if not close_enough(
            coefficient_sum,
            1.0,
        ):
            errors.append(
                f"{assessment_id}: "
                "methodology coefficient "
                "sum is "
                f"{coefficient_sum:.12g}, "
                "expected 1.0"
            )

        seen_origins: set[str] = set()

        adjusted_scores: list[
            float
        ] = []

        contributions = assessment[
            "contributions"
        ]

        for contribution in (
            contributions
        ):

            origin_id = contribution[
                "origin_id"
            ]

            if (
                origin_id
                in seen_origins
            ):
                errors.append(
                    f"{assessment_id}: "
                    "duplicate contribution "
                    f"Origin {origin_id}"
                )

            seen_origins.add(
                origin_id
            )

            if (
                derivative is not None
                and origin_id
                not in set(
                    derivative[
                        "origin_refs"
                    ]
                )
            ):
                errors.append(
                    f"{assessment_id}: "
                    "contribution Origin "
                    f"{origin_id} "
                    "is not declared by "
                    f"Derivative "
                    f"{derivative_id}"
                )

            evidence_ref = contribution[
                "evidence_assessment_ref"
            ]

            if (
                evidence_ref
                not in declared_evidence_refs
            ):
                errors.append(
                    f"{assessment_id}: "
                    "contribution Evidence "
                    "Assessment "
                    f"{evidence_ref} "
                    "is not listed in "
                    "evidence_assessment_refs"
                )

            evidence = (
                evidence_assessments.get(
                    evidence_ref
                )
            )

            if evidence is None:

                errors.append(
                    f"{assessment_id}: "
                    "contribution references "
                    "unknown Evidence "
                    "Assessment "
                    f"{evidence_ref}"
                )

            else:

                if (
                    evidence[
                        "origin_id"
                    ]
                    != origin_id
                ):
                    errors.append(
                        f"{assessment_id}: "
                        "contribution Origin "
                        f"{origin_id} "
                        "does not match "
                        "Evidence Assessment "
                        f"{evidence_ref} "
                        "Origin "
                        f"{evidence['origin_id']}"
                    )

                if (
                    evidence[
                        "derivative_id"
                    ]
                    != derivative_id
                ):
                    errors.append(
                        f"{assessment_id}: "
                        "contribution Evidence "
                        "Assessment "
                        f"{evidence_ref} "
                        "Derivative mismatch"
                    )

                if (
                    evidence[
                        "trace_chain_ref"
                    ]
                    != chain_id
                ):
                    errors.append(
                        f"{assessment_id}: "
                        "contribution Evidence "
                        "Assessment "
                        f"{evidence_ref} "
                        "Trace Chain mismatch"
                    )

                if not close_enough(
                    contribution[
                        "evidence_strength"
                    ],
                    evidence[
                        "evidence_strength"
                    ],
                ):
                    errors.append(
                        f"{assessment_id}: "
                        "evidence_strength "
                        "does not match "
                        "Evidence Assessment "
                        f"{evidence_ref}"
                    )

            expected_raw = sum(
                float(
                    coefficients[
                        field
                    ]
                )
                * float(
                    contribution[
                        field
                    ]
                )
                for field
                in COEFFICIENT_FIELDS
            )

            actual_raw = float(
                contribution[
                    "raw_score"
                ]
            )

            if not close_enough(
                actual_raw,
                expected_raw,
            ):
                errors.append(
                    f"{assessment_id}: "
                    "raw_score mismatch "
                    f"for {origin_id}: "
                    f"{actual_raw:.12g} "
                    "!= "
                    f"{expected_raw:.12g}"
                )

            adjustment = methodology[
                "evidence_adjustment"
            ]

            if adjustment == "none":

                expected_adjusted = (
                    expected_raw
                )

            elif (
                adjustment
                == "multiplicative"
            ):

                expected_adjusted = (
                    expected_raw
                    * float(
                        contribution[
                            "evidence_strength"
                        ]
                    )
                )

            else:

                expected_adjusted = (
                    actual_raw
                )

            actual_adjusted = float(
                contribution[
                    "adjusted_score"
                ]
            )

            if not close_enough(
                actual_adjusted,
                expected_adjusted,
            ):
                errors.append(
                    f"{assessment_id}: "
                    "adjusted_score mismatch "
                    f"for {origin_id}: "
                    f"{actual_adjusted:.12g} "
                    "!= "
                    f"{expected_adjusted:.12g}"
                )

            adjusted_scores.append(
                expected_adjusted
            )

        if (
            assessment[
                "normalization_status"
            ]
            == "normalized"
        ):

            total_adjusted = sum(
                adjusted_scores
            )

            if (
                total_adjusted
                <= EPSILON
            ):
                errors.append(
                    f"{assessment_id}: "
                    "cannot normalize "
                    "zero adjusted "
                    "contribution total"
                )

            else:

                for (
                    contribution,
                    expected_adjusted,
                ) in zip(
                    contributions,
                    adjusted_scores,
                ):

                    expected_weight = (
                        expected_adjusted
                        / total_adjusted
                    )

                    actual_weight = float(
                        contribution[
                            "normalized_weight"
                        ]
                    )

                    if not close_enough(
                        actual_weight,
                        expected_weight,
                    ):
                        errors.append(
                            f"{assessment_id}: "
                            "normalized_weight "
                            "mismatch for "
                            f"{contribution['origin_id']}: "
                            f"{actual_weight:.12g} "
                            "!= "
                            f"{expected_weight:.12g}"
                        )

            weight_sum = sum(
                float(
                    item[
                        "normalized_weight"
                    ]
                )
                for item
                in contributions
            )

            if not close_enough(
                weight_sum,
                1.0,
            ):
                errors.append(
                    f"{assessment_id}: "
                    "normalized contribution "
                    "weights sum to "
                    f"{weight_sum:.12g}, "
                    "expected 1.0"
                )

    # ======================================================
    # Audit
    # CVCP-34 / 35 / 36
    # ======================================================

    for (
        audit_id,
        audit,
    ) in audits.items():

        derivative_id = audit[
            "derivative_id"
        ]

        chain_id = audit[
            "trace_chain_ref"
        ]

        derivative = derivatives.get(
            derivative_id
        )

        if derivative is None:
            errors.append(
                f"{audit_id}: "
                f"unknown Derivative "
                f"{derivative_id}"
            )

        chain = chains.get(
            chain_id
        )

        if chain is None:

            errors.append(
                f"{audit_id}: "
                f"unknown Trace Chain "
                f"{chain_id}"
            )

            chain_trace_refs: set[
                str
            ] = set()

        else:

            chain_trace_refs = set(
                chain[
                    "trace_refs"
                ]
            )

            if (
                chain[
                    "derivative_id"
                ]
                != derivative_id
            ):
                errors.append(
                    f"{audit_id}: "
                    "Trace Chain "
                    "Derivative mismatch"
                )

            if not set(
                audit[
                    "trace_refs"
                ]
            ).issubset(
                chain_trace_refs
            ):
                errors.append(
                    f"{audit_id}: "
                    "Audit references "
                    "Trace outside "
                    "Trace Chain"
                )

        audit_evidence_refs = set(
            audit[
                "evidence_assessment_refs"
            ]
        )

        for evidence_ref in (
            audit_evidence_refs
        ):

            evidence = (
                evidence_assessments.get(
                    evidence_ref
                )
            )

            if evidence is None:

                errors.append(
                    f"{audit_id}: "
                    "unknown Evidence "
                    "Assessment "
                    f"{evidence_ref}"
                )

                continue

            if (
                evidence[
                    "derivative_id"
                ]
                != derivative_id
            ):
                errors.append(
                    f"{audit_id}: "
                    "Evidence Assessment "
                    f"{evidence_ref} "
                    "Derivative mismatch"
                )

            if (
                evidence[
                    "trace_chain_ref"
                ]
                != chain_id
            ):
                errors.append(
                    f"{audit_id}: "
                    "Evidence Assessment "
                    f"{evidence_ref} "
                    "Trace Chain mismatch"
                )

        contribution_ref = audit[
            "contribution_assessment_ref"
        ]

        contribution_assessment = (
            contribution_assessments.get(
                contribution_ref
            )
        )

        if (
            contribution_assessment
            is None
        ):

            errors.append(
                f"{audit_id}: "
                "unknown Contribution "
                "Assessment "
                f"{contribution_ref}"
            )

            expected_weights: dict[
                str,
                float,
            ] = {}

        else:

            if (
                contribution_assessment[
                    "derivative_id"
                ]
                != derivative_id
            ):
                errors.append(
                    f"{audit_id}: "
                    "Contribution Assessment "
                    "Derivative mismatch"
                )

            if (
                contribution_assessment[
                    "trace_chain_ref"
                ]
                != chain_id
            ):
                errors.append(
                    f"{audit_id}: "
                    "Contribution Assessment "
                    "Trace Chain mismatch"
                )

            contribution_evidence_refs = set(
                contribution_assessment[
                    "evidence_assessment_refs"
                ]
            )

            if (
                contribution_evidence_refs
                != audit_evidence_refs
            ):
                errors.append(
                    f"{audit_id}: "
                    "Audit Evidence Assessment "
                    "set does not match "
                    "Contribution Assessment "
                    "Evidence set"
                )

            expected_weights = {
                item[
                    "origin_id"
                ]:
                    float(
                        item[
                            "normalized_weight"
                        ]
                    )
                for item
                in contribution_assessment[
                    "contributions"
                ]
            }

        audit_weights: dict[
            str,
            float,
        ] = {}

        seen_origins: set[str] = set()

        for contribution in audit[
            "contributions"
        ]:

            origin_id = contribution[
                "origin_id"
            ]

            if (
                origin_id
                in seen_origins
            ):
                errors.append(
                    f"{audit_id}: "
                    "duplicate Audit "
                    f"Origin {origin_id}"
                )

            seen_origins.add(
                origin_id
            )

            audit_weights[
                origin_id
            ] = float(
                contribution[
                    "weight"
                ]
            )

            expected_weight = (
                expected_weights.get(
                    origin_id
                )
            )

            if (
                expected_weight
                is None
            ):
                errors.append(
                    f"{audit_id}: "
                    "Audit contribution "
                    f"Origin {origin_id} "
                    "is absent from "
                    "Contribution Assessment"
                )

            elif not close_enough(
                contribution[
                    "weight"
                ],
                expected_weight,
            ):
                errors.append(
                    f"{audit_id}: "
                    "Audit weight mismatch "
                    f"for {origin_id}: "
                    f"{float(contribution['weight']):.12g} "
                    "!= "
                    f"{expected_weight:.12g}"
                )

            for trace_id in contribution[
                "evidence_trace_ids"
            ]:

                if (
                    trace_id
                    not in set(
                        audit[
                            "trace_refs"
                        ]
                    )
                ):
                    errors.append(
                        f"{audit_id}: "
                        "evidence Trace "
                        f"{trace_id} "
                        "is outside Audit "
                        "trace_refs"
                    )

                if (
                    trace_id
                    not in traces
                ):
                    errors.append(
                        f"{audit_id}: "
                        "unknown evidence "
                        f"Trace {trace_id}"
                    )

        if (
            audit[
                "status"
            ]
            in {
                "verified",
                "provisional",
            }
            and expected_weights
            and set(
                audit_weights
            )
            != set(
                expected_weights
            )
        ):
            errors.append(
                f"{audit_id}: "
                "Audit contribution "
                "Origin set does not "
                "match Contribution "
                "Assessment"
            )

        profile = audit[
            "audit_profile"
        ]

        provisional_threshold = float(
            profile[
                "provisional_threshold"
            ]
        )

        verified_threshold = float(
            profile[
                "verified_threshold"
            ]
        )

        if (
            provisional_threshold
            > verified_threshold
        ):
            errors.append(
                f"{audit_id}: "
                "provisional_threshold "
                "must not exceed "
                "verified_threshold"
            )

        expected_confidence = (
            audit_confidence(
                audit
            )
        )

        if (
            expected_confidence
            is not None
            and not close_enough(
                audit[
                    "confidence"
                ],
                expected_confidence,
            )
        ):
            errors.append(
                f"{audit_id}: "
                "confidence mismatch: "
                f"{float(audit['confidence']):.12g} "
                "!= "
                f"{expected_confidence:.12g}"
            )

        confidence = float(
            audit[
                "confidence"
            ]
        )

        status = audit[
            "status"
        ]

        if (
            status
            == "verified"
            and confidence
            < (
                verified_threshold
                - EPSILON
            )
        ):
            errors.append(
                f"{audit_id}: "
                "verified status "
                "requires confidence "
                f">= {verified_threshold}"
            )

        elif (
            status
            == "provisional"
            and (
                confidence
                < (
                    provisional_threshold
                    - EPSILON
                )
                or confidence
                >= (
                    verified_threshold
                    - EPSILON
                )
            )
        ):
            errors.append(
                f"{audit_id}: "
                "provisional status "
                "requires "
                f"{provisional_threshold} "
                "<= confidence < "
                f"{verified_threshold}"
            )

        elif (
            status
            == "rejected"
            and confidence
            >= (
                provisional_threshold
                - EPSILON
            )
        ):
            errors.append(
                f"{audit_id}: "
                "rejected status "
                "requires confidence "
                f"< {provisional_threshold}"
            )

    # ======================================================
    # Royalty
    # CVCP-37 / CVCP-40
    # ======================================================

    for (
        royalty_id,
        royalty,
    ) in royalties.items():

        audit_id = royalty[
            "audit_id"
        ]

        audit = audits.get(
            audit_id
        )

        if audit is None:

            errors.append(
                f"{royalty_id}: "
                f"unknown Audit "
                f"{audit_id}"
            )

            continue

        basis = royalty[
            "royalty_basis"
        ]

        if (
            basis[
                "contribution_assessment_ref"
            ]
            != audit[
                "contribution_assessment_ref"
            ]
        ):
            errors.append(
                f"{royalty_id}: "
                "Royalty contribution "
                "basis does not match "
                "Audit Contribution "
                "Assessment"
            )

        if not close_enough(
            basis[
                "audit_confidence"
            ],
            audit[
                "confidence"
            ],
        ):
            errors.append(
                f"{royalty_id}: "
                "Royalty audit_confidence "
                "does not match Audit"
            )

        if (
            basis[
                "audit_status"
            ]
            != audit[
                "status"
            ]
        ):
            errors.append(
                f"{royalty_id}: "
                "Royalty audit_status "
                f"{basis['audit_status']!r} "
                "does not match "
                "Audit status "
                f"{audit['status']!r}"
            )

        contribution_assessment = (
            contribution_assessments.get(
                basis[
                    "contribution_assessment_ref"
                ]
            )
        )

        if (
            contribution_assessment
            is None
        ):
            errors.append(
                f"{royalty_id}: "
                "unknown Royalty basis "
                "Contribution Assessment "
                f"{basis['contribution_assessment_ref']}"
            )

        audited_weights = {
            item[
                "origin_id"
            ]:
                float(
                    item[
                        "weight"
                    ]
                )
            for item
            in audit[
                "contributions"
            ]
        }

        allocation_origins: set[
            str
        ] = set()

        for allocation in royalty[
            "allocations"
        ]:

            origin_id = allocation[
                "origin_id"
            ]

            if (
                origin_id
                in allocation_origins
            ):
                errors.append(
                    f"{royalty_id}: "
                    "duplicate Royalty "
                    f"Origin {origin_id}"
                )

            allocation_origins.add(
                origin_id
            )

            audited_weight = (
                audited_weights.get(
                    origin_id
                )
            )

            if (
                audited_weight
                is None
            ):
                errors.append(
                    f"{royalty_id}: "
                    "allocation Origin "
                    f"{origin_id} "
                    "was not audited"
                )

                continue

            actual_weight = float(
                allocation[
                    "contribution_weight"
                ]
            )

            if not close_enough(
                actual_weight,
                audited_weight,
            ):
                errors.append(
                    f"{royalty_id}: "
                    "contribution weight "
                    "does not match Audit "
                    f"for {origin_id}"
                )

            expected_amount = (
                float(
                    royalty[
                        "value_generated"
                    ]
                )
                * actual_weight
                * float(
                    allocation[
                        "royalty_rate"
                    ]
                )
            )

            actual_amount = float(
                allocation[
                    "amount"
                ]
            )

            if not close_enough(
                expected_amount,
                actual_amount,
            ):
                errors.append(
                    f"{royalty_id}: "
                    "amount mismatch "
                    f"for {origin_id}: "
                    f"{actual_amount:.12g} "
                    "!= "
                    f"{expected_amount:.12g}"
                )

            origin = origins.get(
                origin_id
            )

            if origin is not None:

                policy = origin[
                    "access_policy"
                ]

                if (
                    policy.get(
                        "royalty_required"
                    )
                    and "royalty_rate"
                    in policy
                ):

                    expected_rate = float(
                        policy[
                            "royalty_rate"
                        ]
                    )

                    actual_rate = float(
                        allocation[
                            "royalty_rate"
                        ]
                    )

                    if not close_enough(
                        expected_rate,
                        actual_rate,
                    ):
                        errors.append(
                            f"{royalty_id}: "
                            "royalty rate "
                            "does not match "
                            "Origin policy "
                            f"for {origin_id}"
                        )

        if (
            audit[
                "status"
            ]
            in {
                "verified",
                "provisional",
            }
            and allocation_origins
            != set(
                audited_weights
            )
        ):
            errors.append(
                f"{royalty_id}: "
                "Royalty allocation "
                "Origin set does not "
                "match Audit"
            )

        settlement_status = royalty[
            "settlement_status"
        ]

        if (
            audit[
                "status"
            ]
            == "provisional"
            and settlement_status
            not in {
                "provisional",
                "not_required",
                "disputed",
            }
        ):
            errors.append(
                f"{royalty_id}: "
                "provisional Audit "
                "cannot enter finalized "
                "settlement flow"
            )

        if (
            audit[
                "status"
            ]
            in {
                "disputed",
                "rejected",
            }
            and settlement_status
            not in {
                "not_required",
                "disputed",
            }
        ):
            errors.append(
                f"{royalty_id}: "
                f"{audit['status']} "
                "Audit cannot enter "
                "settlement flow"
            )

        if (
            settlement_status
            == "settled"
            and audit[
                "status"
            ]
            != "verified"
        ):
            errors.append(
                f"{royalty_id}: "
                "final settlement "
                "requires verified Audit"
            )

    # ======================================================
    # State Transition
    # CVCP-21 / 22 / 23 / 25
    # ======================================================

    for (
        transition_id,
        transition,
    ) in transitions.items():

        pair = (
            transition[
                "previous_status"
            ],
            transition[
                "next_status"
            ],
        )

        if (
            pair
            not in LEGAL_TRANSITIONS
        ):
            errors.append(
                f"{transition_id}: "
                "illegal transition "
                f"{pair[0]} -> "
                f"{pair[1]}"
            )

            continue

        cycle = cycles.get(
            transition[
                "cycle_id"
            ]
        )

        if cycle is None:

            errors.append(
                f"{transition_id}: "
                "unknown Value Cycle "
                f"{transition['cycle_id']}"
            )

            continue

        evidence_refs = set(
            transition[
                "evidence_refs"
            ]
        )

        next_status = transition[
            "next_status"
        ]

        required_refs: set[
            str
        ] = set()

        if (
            next_status
            == "derivative_created"
        ):

            ref = cycle.get(
                "derivative_ref"
            )

            if isinstance(
                ref,
                str,
            ):
                required_refs.add(
                    ref
                )

        elif (
            next_status
            in {
                "trace_recorded",
                "audit_pending",
            }
        ):

            ref = cycle.get(
                "trace_chain_ref"
            )

            if isinstance(
                ref,
                str,
            ):
                required_refs.add(
                    ref
                )

        elif (
            next_status
            in {
                "audit_provisional",
                "audit_verified",
            }
        ):

            ref = cycle.get(
                "audit_ref"
            )

            if isinstance(
                ref,
                str,
            ):
                required_refs.add(
                    ref
                )

        elif (
            next_status
            in {
                "royalty_calculated",
                "settlement_pending",
            }
        ):

            ref = cycle.get(
                "royalty_ref"
            )

            if isinstance(
                ref,
                str,
            ):
                required_refs.add(
                    ref
                )

        elif (
            next_status
            == "settled"
        ):

            royalty_id = cycle.get(
                "royalty_ref"
            )

            royalty = (
                royalties.get(
                    royalty_id
                )
                if isinstance(
                    royalty_id,
                    str,
                )
                else None
            )

            if royalty is None:

                errors.append(
                    f"{transition_id}: "
                    "settled transition "
                    "requires "
                    "Royalty Record"
                )

            else:

                settlement_ref = (
                    royalty.get(
                        "settlement_ref"
                    )
                )

                if not settlement_ref:

                    errors.append(
                        f"{transition_id}: "
                        "settled transition "
                        "requires "
                        "settlement_ref"
                    )

                else:
                    required_refs.add(
                        settlement_ref
                    )

        missing_evidence = (
            required_refs
            - evidence_refs
        )

        if missing_evidence:
            errors.append(
                f"{transition_id}: "
                "required transition "
                "evidence missing: "
                f"{sorted(missing_evidence)}"
            )

    # ======================================================
    # Value Cycle
    # CVCP-24 + v0.3 assessment chain
    # ======================================================

    for (
        cycle_id,
        cycle,
    ) in cycles.items():

        created_at = parse_datetime(
            cycle[
                "created_at"
            ]
        )

        updated_at = parse_datetime(
            cycle[
                "updated_at"
            ]
        )

        if (
            updated_at
            < created_at
        ):
            errors.append(
                f"{cycle_id}: "
                "updated_at precedes "
                "created_at"
            )

        cycle_origins = set(
            cycle[
                "origin_refs"
            ]
        )

        for origin_id in (
            cycle_origins
        ):
            if (
                origin_id
                not in origins
            ):
                errors.append(
                    f"{cycle_id}: "
                    f"unknown Origin "
                    f"{origin_id}"
                )

        derivative_id = cycle.get(
            "derivative_ref"
        )

        derivative = (
            derivatives.get(
                derivative_id
            )
            if isinstance(
                derivative_id,
                str,
            )
            else None
        )

        if (
            derivative_id is not None
            and derivative is None
        ):
            errors.append(
                f"{cycle_id}: "
                "unknown Derivative "
                f"{derivative_id}"
            )

        if (
            derivative is not None
            and cycle_origins
            != set(
                derivative[
                    "origin_refs"
                ]
            )
        ):
            errors.append(
                f"{cycle_id}: "
                "Origin set does not "
                "match Derivative "
                "Origin set"
            )

        chain_id = cycle.get(
            "trace_chain_ref"
        )

        chain = (
            chains.get(
                chain_id
            )
            if isinstance(
                chain_id,
                str,
            )
            else None
        )

        if (
            chain_id is not None
            and chain is None
        ):
            errors.append(
                f"{cycle_id}: "
                "unknown Trace Chain "
                f"{chain_id}"
            )

        if chain is not None:

            if (
                derivative_id is not None
                and chain[
                    "derivative_id"
                ]
                != derivative_id
            ):
                errors.append(
                    f"{cycle_id}: "
                    "Trace Chain "
                    "Derivative mismatch"
                )

            if (
                set(
                    cycle.get(
                        "trace_refs",
                        [],
                    )
                )
                != set(
                    chain[
                        "trace_refs"
                    ]
                )
            ):
                errors.append(
                    f"{cycle_id}: "
                    "cycle Trace set "
                    "does not equal "
                    "Trace Chain set"
                )

        cycle_evidence_refs = set(
            cycle.get(
                "evidence_assessment_refs",
                [],
            )
        )

        for evidence_ref in (
            cycle_evidence_refs
        ):

            evidence = (
                evidence_assessments.get(
                    evidence_ref
                )
            )

            if evidence is None:

                errors.append(
                    f"{cycle_id}: "
                    "unknown Evidence "
                    "Assessment "
                    f"{evidence_ref}"
                )

                continue

            if (
                derivative_id is not None
                and evidence[
                    "derivative_id"
                ]
                != derivative_id
            ):
                errors.append(
                    f"{cycle_id}: "
                    "Evidence Assessment "
                    f"{evidence_ref} "
                    "Derivative mismatch"
                )

            if (
                chain_id is not None
                and evidence[
                    "trace_chain_ref"
                ]
                != chain_id
            ):
                errors.append(
                    f"{cycle_id}: "
                    "Evidence Assessment "
                    f"{evidence_ref} "
                    "Trace Chain mismatch"
                )

        contribution_ref = cycle.get(
            "contribution_assessment_ref"
        )

        contribution_assessment = (
            contribution_assessments.get(
                contribution_ref
            )
            if isinstance(
                contribution_ref,
                str,
            )
            else None
        )

        if (
            contribution_ref is not None
            and contribution_assessment
            is None
        ):
            errors.append(
                f"{cycle_id}: "
                "unknown Contribution "
                "Assessment "
                f"{contribution_ref}"
            )

        if (
            contribution_assessment
            is not None
        ):

            if (
                derivative_id is not None
                and contribution_assessment[
                    "derivative_id"
                ]
                != derivative_id
            ):
                errors.append(
                    f"{cycle_id}: "
                    "Contribution "
                    "Assessment "
                    "Derivative mismatch"
                )

            if (
                chain_id is not None
                and contribution_assessment[
                    "trace_chain_ref"
                ]
                != chain_id
            ):
                errors.append(
                    f"{cycle_id}: "
                    "Contribution "
                    "Assessment "
                    "Trace Chain mismatch"
                )

            if (
                cycle_evidence_refs
                != set(
                    contribution_assessment[
                        "evidence_assessment_refs"
                    ]
                )
            ):
                errors.append(
                    f"{cycle_id}: "
                    "Evidence Assessment "
                    "set does not match "
                    "Contribution "
                    "Assessment Evidence set"
                )

        audit_id = cycle.get(
            "audit_ref"
        )

        audit = (
            audits.get(
                audit_id
            )
            if isinstance(
                audit_id,
                str,
            )
            else None
        )

        if (
            audit_id is not None
            and audit is None
        ):
            errors.append(
                f"{cycle_id}: "
                f"unknown Audit "
                f"{audit_id}"
            )

        if audit is not None:

            if (
                derivative_id is not None
                and audit[
                    "derivative_id"
                ]
                != derivative_id
            ):
                errors.append(
                    f"{cycle_id}: "
                    "Audit Derivative "
                    "mismatch"
                )

            if (
                contribution_ref
                is not None
                and audit[
                    "contribution_assessment_ref"
                ]
                != contribution_ref
            ):
                errors.append(
                    f"{cycle_id}: "
                    "Audit Contribution "
                    "Assessment mismatch"
                )

            if (
                cycle_evidence_refs
                != set(
                    audit[
                        "evidence_assessment_refs"
                    ]
                )
            ):
                errors.append(
                    f"{cycle_id}: "
                    "Audit Evidence "
                    "Assessment set "
                    "mismatch"
                )

        royalty_id = cycle.get(
            "royalty_ref"
        )

        royalty = (
            royalties.get(
                royalty_id
            )
            if isinstance(
                royalty_id,
                str,
            )
            else None
        )

        if (
            royalty_id is not None
            and royalty is None
        ):
            errors.append(
                f"{cycle_id}: "
                "unknown Royalty "
                f"{royalty_id}"
            )

        if royalty is not None:

            if (
                audit_id is not None
                and royalty[
                    "audit_id"
                ]
                != audit_id
            ):
                errors.append(
                    f"{cycle_id}: "
                    "Royalty does not "
                    "derive from "
                    "cycle Audit"
                )

            if (
                contribution_ref
                is not None
                and royalty[
                    "royalty_basis"
                ][
                    "contribution_assessment_ref"
                ]
                != contribution_ref
            ):
                errors.append(
                    f"{cycle_id}: "
                    "Royalty Contribution "
                    "Assessment basis "
                    "mismatch"
                )

        transition_sequence: list[
            dict[str, Any]
        ] = []

        for transition_id in cycle.get(
            "transition_refs",
            [],
        ):

            transition = transitions.get(
                transition_id
            )

            if transition is None:

                errors.append(
                    f"{cycle_id}: "
                    "unknown State "
                    "Transition "
                    f"{transition_id}"
                )

                continue

            if (
                transition[
                    "cycle_id"
                ]
                != cycle_id
            ):
                errors.append(
                    f"{cycle_id}: "
                    "State Transition "
                    f"{transition_id} "
                    "belongs to another "
                    "Value Cycle"
                )

            transition_sequence.append(
                transition
            )

        for (
            previous,
            current,
        ) in zip(
            transition_sequence,
            transition_sequence[
                1:
            ],
        ):

            if (
                previous[
                    "next_status"
                ]
                != current[
                    "previous_status"
                ]
            ):
                errors.append(
                    f"{cycle_id}: "
                    "broken transition "
                    "continuity "
                    f"{previous['transition_id']} "
                    "-> "
                    f"{current['transition_id']}"
                )

            if (
                parse_datetime(
                    previous[
                        "transitioned_at"
                    ]
                )
                >
                parse_datetime(
                    current[
                        "transitioned_at"
                    ]
                )
            ):
                errors.append(
                    f"{cycle_id}: "
                    "transition timestamp "
                    "order violation"
                )

        if transition_sequence:

            latest_status = (
                transition_sequence[
                    -1
                ][
                    "next_status"
                ]
            )

            if (
                latest_status
                != cycle[
                    "cycle_status"
                ]
            ):
                errors.append(
                    f"{cycle_id}: "
                    "cycle_status mismatch: "
                    f"latest={latest_status}, "
                    "current="
                    f"{cycle['cycle_status']}"
                )

        status = cycle[
            "cycle_status"
        ]

        if (
            status
            == "audit_provisional"
            and audit is not None
            and audit[
                "status"
            ]
            != "provisional"
        ):
            errors.append(
                f"{cycle_id}: "
                "audit_provisional cycle "
                "requires provisional "
                "Audit"
            )

        if status in {
            "audit_verified",
            "royalty_calculated",
            "settlement_pending",
            "settled",
        }:

            if (
                audit is not None
                and audit[
                    "status"
                ]
                != "verified"
            ):
                errors.append(
                    f"{cycle_id}: "
                    "cycle status "
                    f"{status!r} "
                    "requires verified "
                    "Audit"
                )

        if (
            status
            == "settlement_pending"
            and royalty is not None
            and royalty[
                "settlement_status"
            ]
            not in {
                "pending",
                "processing",
            }
        ):
            errors.append(
                f"{cycle_id}: "
                "settlement_pending "
                "cycle requires pending "
                "or processing Royalty"
            )

        if (
            status
            == "settled"
            and royalty is not None
            and royalty[
                "settlement_status"
            ]
            != "settled"
        ):
            errors.append(
                f"{cycle_id}: "
                "settled cycle requires "
                "settled Royalty"
            )

    return errors


def print_errors(
    errors: list[str],
) -> None:

    for error in errors:
        print(
            f"  - {error}"
        )


def main() -> int:

    print(
        "=== Civilization Value Cycle "
        "Protocol v0.3 Validation ==="
    )

    try:
        validators = load_schemas()

    except Exception as exc:
        print(
            "[fatal] schema loading "
            f"failed: {exc}"
        )

        return 2

    for (
        record_type,
        path,
    ) in SCHEMA_FILES.items():

        print(
            f"schema [{record_type}]: "
            f"{path.relative_to(ROOT)}"
        )

    pass_paths = example_files(
        PASS_DIR
    )

    fail_paths = example_files(
        FAIL_DIR
    )

    if not pass_paths:
        print(
            "[fatal] no pass "
            "examples found"
        )

        return 2

    if not fail_paths:
        print(
            "[fatal] no fail "
            "examples found"
        )

        return 2

    unexpected = 0

    pass_records: list[
        dict[str, Any]
    ] = []

    print(
        "\n[pass examples]\n"
    )

    for path in pass_paths:

        print(
            f"- "
            f"{path.relative_to(ROOT)}"
        )

        try:
            document = load_document(
                path
            )

            records = expand_fixture(
                document
            )

        except ValidationFailure as exc:

            print(
                f"[parse-error] "
                f"{exc}\n"
            )

            unexpected += 1

            continue

        file_failed = False

        for record in records:

            errors = schema_errors(
                record,
                validators,
            )

            if errors:

                print(
                    "[schema-error]"
                )

                print_errors(
                    errors
                )

                file_failed = True

        if file_failed:

            unexpected += 1

            print()

            continue

        print(
            "[schema-ok]"
        )

        pass_records.extend(
            records
        )

        print()

    pass_semantic = (
        semantic_errors(
            pass_records
        )
    )

    if pass_semantic:

        print(
            "[pass semantic errors]"
        )

        print_errors(
            pass_semantic
        )

        unexpected += len(
            pass_semantic
        )

    else:

        print(
            "[semantic-ok] "
            "pass example set\n"
        )

    print(
        "[fail examples]\n"
    )

    expected_failures = 0

    for path in fail_paths:

        print(
            f"- "
            f"{path.relative_to(ROOT)}"
        )

        try:

            document = load_document(
                path
            )

            records = expand_fixture(
                document
            )

        except ValidationFailure as exc:

            print(
                "[expected-parse-failure] "
                f"{exc}\n"
            )

            expected_failures += 1

            continue

        all_schema_errors: list[
            str
        ] = []

        for record in records:

            all_schema_errors.extend(
                schema_errors(
                    record,
                    validators,
                )
            )

        if all_schema_errors:

            print(
                "[expected-schema-failure]"
            )

            print_errors(
                all_schema_errors
            )

            print()

            expected_failures += 1

            continue

        print(
            "[schema-ok]"
        )

        scenario_records = (
            pass_records
            + records
        )

        errors = semantic_errors(
            scenario_records
        )

        if errors:

            print(
                "[expected-semantic-failure]"
            )

            print_errors(
                errors
            )

            print()

            expected_failures += 1

        else:

            print(
                "[unexpected-pass]\n"
            )

            unexpected += 1

    print(
        "=== Summary ==="
    )

    print(
        "pass example files: "
        f"{len(pass_paths)}"
    )

    print(
        "fail example files: "
        f"{len(fail_paths)}"
    )

    print(
        "expected failures observed: "
        f"{expected_failures}"
    )

    print(
        "unexpected results: "
        f"{unexpected}"
    )

    if unexpected:

        print(
            "[validation-failed]"
        )

        return 1

    print(
        "[validation-passed]"
    )

    return 0


if __name__ == "__main__":
    sys.exit(
        main()
    )
  

