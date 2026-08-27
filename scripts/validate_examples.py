#!/usr/bin/env python3
from __future__ import annotations

import json
import math
import sys
from collections import defaultdict, deque
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

    "settlement_request_record":
        SCHEMA_DIR / "settlement-request-record.schema.json",

    "settlement_receipt_record":
        SCHEMA_DIR / "settlement-receipt-record.schema.json",

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
    "settlement_request_record":
        "settlement_request_id",
    "settlement_receipt_record":
        "settlement_receipt_id",
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
        "settlement_processing",
    ),
    (
        "settlement_pending",
        "disputed",
    ),
    (
        "settlement_processing",
        "settled",
    ),
    (
        "settlement_processing",
        "settlement_failed",
    ),
    (
        "settlement_processing",
        "disputed",
    ),
    (
        "settlement_failed",
        "settlement_pending",
    ),
    (
        "settled",
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


def unit_key(
    value_unit: dict[str, Any],
) -> tuple[str, str]:

    return (
        str(
            value_unit["type"]
        ),
        str(
            value_unit["code"]
        ),
    )


def royalty_amounts_by_origin(
    royalty: dict[str, Any],
) -> dict[str, float]:

    result: dict[
        str,
        float,
    ] = defaultdict(float)

    for allocation in royalty[
        "allocations"
    ]:
        result[
            allocation[
                "origin_id"
            ]
        ] += float(
            allocation[
                "amount"
            ]
        )

    return dict(result)


def request_amounts_by_origin(
    request: dict[str, Any],
) -> dict[str, float]:

    result: dict[
        str,
        float,
    ] = defaultdict(float)

    for allocation in request[
        "allocations"
    ]:
        result[
            allocation[
                "origin_id"
            ]
        ] += float(
            allocation[
                "amount"
            ]
        )

    return dict(result)


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

    settlement_requests = index[
        "settlement_request_record"
    ]

    settlement_receipts = index[
        "settlement_receipt_record"
    ]

    transitions = index[
        "state_transition_record"
    ]

    cycles = index[
        "value_cycle_record"
    ]

    # ======================================================
    # Origin / Derivative
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
    # Trace parents
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
    # Trace Chain
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

        chain = chains.get(
            chain_id
        )

        if derivative is None:
            errors.append(
                f"{assessment_id}: "
                f"unknown Derivative "
                f"{derivative_id}"
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

        chain = chains.get(
            chain_id
        )

        if derivative is None:
            errors.append(
                f"{assessment_id}: "
                f"unknown Derivative "
                f"{derivative_id}"
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

        chain = chains.get(
            chain_id
        )

        if (
            derivative_id
            not in derivatives
        ):
            errors.append(
                f"{audit_id}: "
                f"unknown Derivative "
                f"{derivative_id}"
            )

        if chain is None:

            errors.append(
                f"{audit_id}: "
                f"unknown Trace Chain "
                f"{chain_id}"
            )

        else:

            if not set(
                audit[
                    "trace_refs"
                ]
            ).issubset(
                set(
                    chain[
                        "trace_refs"
                    ]
                )
            ):
                errors.append(
                    f"{audit_id}: "
                    "Audit references "
                    "Trace outside "
                    "Trace Chain"
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

        for contribution in audit[
            "contributions"
        ]:

            origin_id = contribution[
                "origin_id"
            ]

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
                is not None
                and not close_enough(
                    contribution[
                        "weight"
                    ],
                    expected_weight,
                )
            ):
                errors.append(
                    f"{audit_id}: "
                    "Audit weight mismatch "
                    f"for {origin_id}: "
                    f"{float(contribution['weight']):.12g} "
                    "!= "
                    f"{expected_weight:.12g}"
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
            < verified_threshold
            - EPSILON
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
            and not (
                provisional_threshold
                - EPSILON
                <= confidence
                < verified_threshold
                - EPSILON
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

    # ======================================================
    # Royalty
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

        for allocation in royalty[
            "allocations"
        ]:

            origin_id = allocation[
                "origin_id"
            ]

            audited_weight = (
                audited_weights.get(
                    origin_id
                )
            )

            if audited_weight is None:
                continue

            expected_amount = (
                float(
                    royalty[
                        "value_generated"
                    ]
                )
                * float(
                    allocation[
                        "contribution_weight"
                    ]
                )
                * float(
                    allocation[
                        "royalty_rate"
                    ]
                )
            )

            if not close_enough(
                allocation[
                    "amount"
                ],
                expected_amount,
            ):
                errors.append(
                    f"{royalty_id}: "
                    "amount mismatch "
                    f"for {origin_id}"
                )

    # ======================================================
    # Settlement Request
    # CVCP-41〜46
    # ======================================================

    idempotency_map: dict[
        str,
        list[str],
    ] = defaultdict(list)

    for (
        request_id,
        request,
    ) in settlement_requests.items():

        idempotency_map[
            request[
                "idempotency_key"
            ]
        ].append(
            request_id
        )

        royalty_id = request[
            "royalty_id"
        ]

        audit_id = request[
            "audit_id"
        ]

        royalty = royalties.get(
            royalty_id
        )

        audit = audits.get(
            audit_id
        )

        if royalty is None:

            errors.append(
                f"{request_id}: "
                f"unknown Royalty "
                f"{royalty_id}"
            )

        if audit is None:

            errors.append(
                f"{request_id}: "
                f"unknown Audit "
                f"{audit_id}"
            )

        if (
            audit is not None
            and audit[
                "status"
            ]
            != "verified"
        ):
            errors.append(
                f"{request_id}: "
                "Settlement Request "
                "requires verified Audit, "
                f"got {audit['status']}"
            )

        if royalty is not None:

            if (
                royalty[
                    "audit_id"
                ]
                != audit_id
            ):
                errors.append(
                    f"{request_id}: "
                    "request audit_id "
                    "does not match "
                    "Royalty audit_id"
                )

            if (
                royalty[
                    "royalty_basis"
                ][
                    "audit_status"
                ]
                != "verified"
            ):
                errors.append(
                    f"{request_id}: "
                    "Settlement Request "
                    "requires verified "
                    "Royalty basis"
                )

            if (
                unit_key(
                    request[
                        "value_unit"
                    ]
                )
                !=
                unit_key(
                    royalty[
                        "value_unit"
                    ]
                )
            ):
                errors.append(
                    f"{request_id}: "
                    "Settlement Request "
                    "value_unit does not "
                    "match Royalty"
                )

            request_amounts = (
                request_amounts_by_origin(
                    request
                )
            )

            royalty_amounts = (
                royalty_amounts_by_origin(
                    royalty
                )
            )

            if (
                set(
                    request_amounts
                )
                !=
                set(
                    royalty_amounts
                )
            ):
                errors.append(
                    f"{request_id}: "
                    "Settlement Request "
                    "Origin set does not "
                    "match Royalty"
                )

            for origin_id in sorted(
                set(
                    request_amounts
                )
                |
                set(
                    royalty_amounts
                )
            ):

                request_amount = (
                    request_amounts.get(
                        origin_id
                    )
                )

                royalty_amount = (
                    royalty_amounts.get(
                        origin_id
                    )
                )

                if (
                    request_amount is None
                    or royalty_amount is None
                ):
                    continue

                if not close_enough(
                    request_amount,
                    royalty_amount,
                ):
                    errors.append(
                        f"{request_id}: "
                        "Settlement Request "
                        "amount mismatch "
                        f"for {origin_id}: "
                        f"{request_amount:.12g} "
                        "!= "
                        f"{royalty_amount:.12g}"
                    )

        if (
            request[
                "execution_authority"
            ]
            != "external"
        ):
            errors.append(
                f"{request_id}: "
                "execution_authority "
                "must be external"
            )

        if not request[
            "authorization_refs"
        ]:
            errors.append(
                f"{request_id}: "
                "authorization_refs "
                "must not be empty"
            )

        if (
            "expires_at"
            in request
            and parse_datetime(
                request[
                    "expires_at"
                ]
            )
            <= parse_datetime(
                request[
                    "requested_at"
                ]
            )
        ):
            errors.append(
                f"{request_id}: "
                "expires_at must be "
                "after requested_at"
            )

        allocation_ids: set[
            str
        ] = set()

        for allocation in request[
            "allocations"
        ]:

            allocation_id = allocation[
                "allocation_id"
            ]

            if (
                allocation_id
                in allocation_ids
            ):
                errors.append(
                    f"{request_id}: "
                    "duplicate settlement "
                    "allocation_id "
                    f"{allocation_id}"
                )

            allocation_ids.add(
                allocation_id
            )

    for (
        key,
        request_ids,
    ) in idempotency_map.items():

        if len(
            request_ids
        ) > 1:
            errors.append(
                "duplicate settlement "
                f"idempotency_key {key}: "
                f"{sorted(request_ids)}"
            )

    # ======================================================
    # Settlement Receipt
    # CVCP-47〜54 / 58
    # ======================================================

    receipts_by_request: dict[
        str,
        list[dict[str, Any]],
    ] = defaultdict(list)

    for (
        receipt_id,
        receipt,
    ) in settlement_receipts.items():

        request_id = receipt[
            "settlement_request_id"
        ]

        receipts_by_request[
            request_id
        ].append(
            receipt
        )

        request = settlement_requests.get(
            request_id
        )

        if request is None:

            errors.append(
                f"{receipt_id}: "
                "unknown Settlement "
                f"Request {request_id}"
            )

            continue

        if (
            receipt[
                "royalty_id"
            ]
            != request[
                "royalty_id"
            ]
        ):
            errors.append(
                f"{receipt_id}: "
                "Receipt royalty_id "
                "does not match "
                "Settlement Request"
            )

        requested_by_id = {
            allocation[
                "allocation_id"
            ]:
                allocation
            for allocation
            in request[
                "allocations"
            ]
        }

        seen_allocation_ids: set[
            str
        ] = set()

        for executed in receipt[
            "executed_allocations"
        ]:

            allocation_id = executed[
                "allocation_id"
            ]

            if (
                allocation_id
                in seen_allocation_ids
            ):
                errors.append(
                    f"{receipt_id}: "
                    "duplicate executed "
                    "allocation_id "
                    f"{allocation_id}"
                )

            seen_allocation_ids.add(
                allocation_id
            )

            requested = (
                requested_by_id.get(
                    allocation_id
                )
            )

            if requested is None:

                errors.append(
                    f"{receipt_id}: "
                    "extra executed "
                    "allocation "
                    f"{allocation_id} "
                    "not present in "
                    "Settlement Request"
                )

                continue

            if (
                executed[
                    "origin_id"
                ]
                != requested[
                    "origin_id"
                ]
            ):
                errors.append(
                    f"{receipt_id}: "
                    f"allocation "
                    f"{allocation_id} "
                    "Origin mismatch"
                )

            if (
                executed[
                    "beneficiary_id"
                ]
                != requested[
                    "beneficiary_id"
                ]
            ):
                errors.append(
                    f"{receipt_id}: "
                    f"allocation "
                    f"{allocation_id} "
                    "beneficiary mismatch"
                )

            if not close_enough(
                executed[
                    "requested_amount"
                ],
                requested[
                    "amount"
                ],
            ):
                errors.append(
                    f"{receipt_id}: "
                    f"allocation "
                    f"{allocation_id} "
                    "requested_amount "
                    "mismatch"
                )

            if (
                receipt[
                    "execution_status"
                ]
                == "settled"
            ):

                if (
                    executed[
                        "status"
                    ]
                    != "settled"
                ):
                    errors.append(
                        f"{receipt_id}: "
                        "settled Receipt "
                        "requires settled "
                        "allocation "
                        f"{allocation_id}"
                    )

                if not close_enough(
                    executed[
                        "executed_amount"
                    ],
                    requested[
                        "amount"
                    ],
                ):
                    errors.append(
                        f"{receipt_id}: "
                        "executed amount "
                        "mismatch for "
                        f"{allocation_id}: "
                        f"{float(executed['executed_amount']):.12g} "
                        "!= "
                        f"{float(requested['amount']):.12g}"
                    )

        request_ids = set(
            requested_by_id
        )

        if (
            receipt[
                "execution_status"
            ]
            == "settled"
            and seen_allocation_ids
            != request_ids
        ):

            missing = (
                request_ids
                - seen_allocation_ids
            )

            extra = (
                seen_allocation_ids
                - request_ids
            )

            if missing:
                errors.append(
                    f"{receipt_id}: "
                    "settled Receipt "
                    "missing allocation(s): "
                    f"{sorted(missing)}"
                )

            if extra:
                errors.append(
                    f"{receipt_id}: "
                    "settled Receipt has "
                    "extra allocation(s): "
                    f"{sorted(extra)}"
                )

        if (
            receipt[
                "execution_status"
            ]
            == "settled"
            and not receipt.get(
                "external_transaction_ref"
            )
        ):
            errors.append(
                f"{receipt_id}: "
                "settled Receipt "
                "requires "
                "external_transaction_ref"
            )

        if (
            "supersedes_ref"
            in receipt
        ):

            superseded_id = receipt[
                "supersedes_ref"
            ]

            superseded = (
                settlement_receipts.get(
                    superseded_id
                )
            )

            if superseded is None:

                errors.append(
                    f"{receipt_id}: "
                    "supersedes unknown "
                    "Settlement Receipt "
                    f"{superseded_id}"
                )

            elif (
                superseded[
                    "settlement_request_id"
                ]
                != request_id
            ):
                errors.append(
                    f"{receipt_id}: "
                    "superseded Receipt "
                    "belongs to another "
                    "Settlement Request"
                )

    for (
        request_id,
        request_receipts,
    ) in receipts_by_request.items():

        settled_receipts = [
            receipt
            for receipt
            in request_receipts
            if (
                receipt[
                    "execution_status"
                ]
                == "settled"
            )
        ]

        if (
            len(
                settled_receipts
            )
            > 1
        ):
            errors.append(
                f"{request_id}: "
                "multiple settled "
                "Settlement Receipts: "
                f"{[
                    item['settlement_receipt_id']
                    for item
                    in settled_receipts
                ]}"
            )

    # ======================================================
    # Royalty ↔ Settlement
    # ======================================================

    for (
        royalty_id,
        royalty,
    ) in royalties.items():

        request_ref = royalty.get(
            "settlement_request_ref"
        )

        receipt_refs = royalty.get(
            "settlement_receipt_refs",
            [],
        )

        request = (
            settlement_requests.get(
                request_ref
            )
            if isinstance(
                request_ref,
                str,
            )
            else None
        )

        if (
            request_ref is not None
            and request is None
        ):
            errors.append(
                f"{royalty_id}: "
                "unknown "
                "settlement_request_ref "
                f"{request_ref}"
            )

        referenced_receipts: list[
            dict[str, Any]
        ] = []

        for receipt_ref in (
            receipt_refs
        ):

            receipt = (
                settlement_receipts.get(
                    receipt_ref
                )
            )

            if receipt is None:

                errors.append(
                    f"{royalty_id}: "
                    "unknown Settlement "
                    f"Receipt {receipt_ref}"
                )

                continue

            referenced_receipts.append(
                receipt
            )

            if (
                receipt[
                    "royalty_id"
                ]
                != royalty_id
            ):
                errors.append(
                    f"{royalty_id}: "
                    "Settlement Receipt "
                    f"{receipt_ref} "
                    "belongs to another "
                    "Royalty"
                )

        status = royalty[
            "settlement_status"
        ]

        if (
            status
            == "processing"
            and not any(
                receipt[
                    "execution_status"
                ]
                == "processing"
                for receipt
                in referenced_receipts
            )
        ):
            errors.append(
                f"{royalty_id}: "
                "processing Royalty "
                "requires processing "
                "Settlement Receipt"
            )

        if (
            status
            == "settled"
            and not any(
                receipt[
                    "execution_status"
                ]
                == "settled"
                for receipt
                in referenced_receipts
            )
        ):
            errors.append(
                f"{royalty_id}: "
                "settled Royalty "
                "requires settled "
                "Settlement Receipt"
            )

        if (
            status
            == "failed"
            and not any(
                receipt[
                    "execution_status"
                ]
                == "failed"
                for receipt
                in referenced_receipts
            )
        ):
            errors.append(
                f"{royalty_id}: "
                "failed Royalty "
                "requires failed "
                "Settlement Receipt"
            )

    # ======================================================
    # State Transition
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

        if (
            next_status
            == "settlement_pending"
        ):

            request_ref = cycle.get(
                "settlement_request_ref"
            )

            if (
                isinstance(
                    request_ref,
                    str,
                )
                and request_ref
                not in evidence_refs
            ):
                errors.append(
                    f"{transition_id}: "
                    "settlement_pending "
                    "transition must cite "
                    "Settlement Request"
                )

        if next_status in {
            "settlement_processing",
            "settlement_failed",
            "settled",
        }:

            expected_status = {
                "settlement_processing":
                    "processing",
                "settlement_failed":
                    "failed",
                "settled":
                    "settled",
            }[
                next_status
            ]

            matching = []

            for receipt_ref in cycle.get(
                "settlement_receipt_refs",
                [],
            ):

                receipt = (
                    settlement_receipts.get(
                        receipt_ref
                    )
                )

                if (
                    receipt is not None
                    and receipt[
                        "execution_status"
                    ]
                    == expected_status
                ):
                    matching.append(
                        receipt_ref
                    )

            if not matching:

                errors.append(
                    f"{transition_id}: "
                    f"{next_status} "
                    "transition requires "
                    f"{expected_status} "
                    "Settlement Receipt"
                )

            elif not (
                set(
                    matching
                )
                & evidence_refs
            ):
                errors.append(
                    f"{transition_id}: "
                    "transition evidence "
                    "must cite a "
                    f"{expected_status} "
                    "Settlement Receipt"
                )

    # ======================================================
    # Value Cycle
    # ======================================================

    for (
        cycle_id,
        cycle,
    ) in cycles.items():

        if (
            parse_datetime(
                cycle[
                    "updated_at"
                ]
            )
            <
            parse_datetime(
                cycle[
                    "created_at"
                ]
            )
        ):
            errors.append(
                f"{cycle_id}: "
                "updated_at precedes "
                "created_at"
            )

        request_id = cycle.get(
            "settlement_request_ref"
        )

        request = (
            settlement_requests.get(
                request_id
            )
            if isinstance(
                request_id,
                str,
            )
            else None
        )

        cycle_receipts: list[
            dict[str, Any]
        ] = []

        for receipt_ref in cycle.get(
            "settlement_receipt_refs",
            [],
        ):

            receipt = (
                settlement_receipts.get(
                    receipt_ref
                )
            )

            if receipt is None:

                errors.append(
                    f"{cycle_id}: "
                    "unknown Settlement "
                    f"Receipt {receipt_ref}"
                )

                continue

            cycle_receipts.append(
                receipt
            )

            if (
                request_id is not None
                and receipt[
                    "settlement_request_id"
                ]
                != request_id
            ):
                errors.append(
                    f"{cycle_id}: "
                    "Settlement Receipt "
                    f"{receipt_ref} "
                    "Request mismatch"
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
                    f"Transition "
                    f"{transition_id}"
                )

                continue

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

        if status in {
            "settlement_pending",
            "settlement_processing",
            "settlement_failed",
            "settled",
        }:

            if request is None:
                errors.append(
                    f"{cycle_id}: "
                    f"{status} cycle "
                    "requires Settlement "
                    "Request"
                )

        if (
            status
            == "settlement_processing"
            and not any(
                receipt[
                    "execution_status"
                ]
                == "processing"
                for receipt
                in cycle_receipts
            )
        ):
            errors.append(
                f"{cycle_id}: "
                "settlement_processing "
                "cycle requires "
                "processing Receipt"
            )

        if (
            status
            == "settlement_failed"
            and not any(
                receipt[
                    "execution_status"
                ]
                == "failed"
                for receipt
                in cycle_receipts
            )
        ):
            errors.append(
                f"{cycle_id}: "
                "settlement_failed "
                "cycle requires "
                "failed Receipt"
            )

        if (
            status
            == "settled"
            and not any(
                receipt[
                    "execution_status"
                ]
                == "settled"
                for receipt
                in cycle_receipts
            )
        ):
            errors.append(
                f"{cycle_id}: "
                "settled cycle "
                "requires settled "
                "Receipt"
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
        "Protocol v0.4 Validation ==="
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

            errs = schema_errors(
                record,
                validators,
            )

            if errs:

                print(
                    "[schema-error]"
                )

                print_errors(
                    errs
                )

                file_failed = True

        if file_failed:

            unexpected += 1

            print()

            continue

        print(
            "[schema-ok]\n"
        )

        pass_records.extend(
            records
        )

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

        errs = semantic_errors(
            scenario_records
        )

        if errs:

            print(
                "[expected-semantic-failure]"
            )

            print_errors(
                errs
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
