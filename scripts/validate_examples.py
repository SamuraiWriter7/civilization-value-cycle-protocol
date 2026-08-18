#!/usr/bin/env python3
from __future__ import annotations

import json
import math
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

import yaml
from jsonschema import Draft202012Validator, FormatChecker


ROOT = Path(__file__).resolve().parents[1]

SCHEMA_DIR = ROOT / "schemas"
PASS_DIR = ROOT / "examples" / "pass"
FAIL_DIR = ROOT / "examples" / "fail"


SCHEMA_FILES = {
    "origin_record": SCHEMA_DIR / "origin-record.schema.json",
    "derivative_record": SCHEMA_DIR / "derivative-record.schema.json",
    "trace_record": SCHEMA_DIR / "trace-record.schema.json",
    "audit_record": SCHEMA_DIR / "audit-record.schema.json",
    "royalty_record": SCHEMA_DIR / "royalty-record.schema.json",
    "value_cycle_record": SCHEMA_DIR / "value-cycle-record.schema.json",
}


ID_FIELDS = {
    "origin_record": "origin_id",
    "derivative_record": "derivative_id",
    "trace_record": "trace_id",
    "audit_record": "audit_id",
    "royalty_record": "royalty_id",
    "value_cycle_record": "cycle_id",
}


EPSILON = 1e-9


class ValidationFailure(Exception):
    pass


def load_data(path: Path) -> dict[str, Any]:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ValidationFailure(
            f"cannot read {path}: {exc}"
        ) from exc

    try:
        if path.suffix.lower() == ".json":
            data = json.loads(text)
        else:
            data = yaml.safe_load(text)

    except (json.JSONDecodeError, yaml.YAMLError) as exc:
        raise ValidationFailure(
            f"cannot parse {path}: {exc}"
        ) from exc

    if not isinstance(data, dict):
        raise ValidationFailure(
            f"{path}: top-level document must be an object"
        )

    return data


def example_files(directory: Path) -> list[Path]:
    paths: list[Path] = []

    for suffix in ("*.yaml", "*.yml", "*.json"):
        paths.extend(directory.glob(suffix))

    return sorted(
        set(paths),
        key=lambda path: path.name,
    )


def json_path(parts: Iterable[Any]) -> str:
    result = "$"

    for part in parts:
        if isinstance(part, int):
            result += f"[{part}]"
        else:
            result += f".{part}"

    return result


def load_schemas() -> dict[str, Draft202012Validator]:
    validators: dict[str, Draft202012Validator] = {}

    for record_type, path in SCHEMA_FILES.items():
        schema = load_data(path)

        Draft202012Validator.check_schema(schema)

        validators[record_type] = Draft202012Validator(
            schema,
            format_checker=FormatChecker(),
        )

    return validators


def schema_errors(
    document: dict[str, Any],
    validators: dict[str, Draft202012Validator],
) -> list[str]:

    record_type = document.get("record_type")

    if record_type not in validators:
        return [
            "$.record_type: "
            f"unknown or missing record_type {record_type!r}"
        ]

    errors = sorted(
        validators[record_type].iter_errors(document),
        key=lambda error: (
            list(error.absolute_path),
            error.message,
        ),
    )

    return [
        f"{json_path(error.absolute_path)}: {error.message}"
        for error in errors
    ]


def parse_datetime(value: str) -> datetime:
    if value.endswith("Z"):
        value = value[:-1] + "+00:00"

    return datetime.fromisoformat(value)


def build_index(
    records: list[tuple[Path, dict[str, Any]]],
) -> tuple[
    dict[str, dict[str, tuple[Path, dict[str, Any]]]],
    list[str],
]:

    index: dict[
        str,
        dict[str, tuple[Path, dict[str, Any]]],
    ] = {
        record_type: {}
        for record_type in ID_FIELDS
    }

    errors: list[str] = []

    for path, document in records:
        record_type = document.get("record_type")
        id_field = ID_FIELDS.get(record_type)

        if id_field is None:
            continue

        record_id = document.get(id_field)

        if not isinstance(record_id, str):
            continue

        if record_id in index[record_type]:
            previous_path, _ = index[record_type][record_id]

            errors.append(
                f"{path.name}: duplicate {id_field} "
                f"{record_id!r}; already defined by "
                f"{previous_path.name}"
            )

            continue

        index[record_type][record_id] = (
            path,
            document,
        )

    return index, errors


def semantic_errors(
    records: list[tuple[Path, dict[str, Any]]],
) -> list[str]:

    index, errors = build_index(records)

    origins = index["origin_record"]
    derivatives = index["derivative_record"]
    traces = index["trace_record"]
    audits = index["audit_record"]
    royalties = index["royalty_record"]

    # ---------------------------------------------------------
    # CVCP-01 / CVCP-07
    # Derivative -> Origin existence and access policy
    # ---------------------------------------------------------

    for derivative_id, (path, derivative) in derivatives.items():

        compliance = {
            item["origin_id"]: item
            for item in derivative.get(
                "policy_compliance",
                [],
            )
            if isinstance(item, dict)
            and isinstance(
                item.get("origin_id"),
                str,
            )
        }

        for origin_id in derivative.get(
            "origin_refs",
            [],
        ):

            origin_entry = origins.get(origin_id)

            if origin_entry is None:
                errors.append(
                    f"{path.name}: derivative "
                    f"{derivative_id} references unknown "
                    f"Origin {origin_id}"
                )
                continue

            _, origin = origin_entry

            reference_policy = (
                origin["access_policy"]["reference"]
            )

            if reference_policy == "deny":
                errors.append(
                    f"{path.name}: derivative "
                    f"{derivative_id} violates Origin "
                    f"reference policy for {origin_id}"
                )

            if reference_policy == "conditional":
                check = compliance.get(origin_id)

                if (
                    check is None
                    or check.get("status") != "satisfied"
                ):
                    errors.append(
                        f"{path.name}: conditional Origin "
                        f"{origin_id} requires "
                        "policy_compliance status "
                        "'satisfied'"
                    )

    # ---------------------------------------------------------
    # CVCP-02 / CVCP-08
    # Trace -> Derivative and ordering
    # ---------------------------------------------------------

    traces_by_derivative: dict[
        str,
        list[tuple[Path, dict[str, Any]]],
    ] = defaultdict(list)

    for trace_id, (path, trace) in traces.items():

        derivative_id = trace["derivative_id"]

        if derivative_id not in derivatives:
            errors.append(
                f"{path.name}: Trace {trace_id} "
                f"references unknown Derivative "
                f"{derivative_id}"
            )

        traces_by_derivative[
            derivative_id
        ].append(
            (path, trace)
        )

    for derivative_id, group in (
        traces_by_derivative.items()
    ):

        by_sequence: dict[int, Path] = {}

        ordered = sorted(
            group,
            key=lambda item: item[1]["sequence"],
        )

        previous_time: datetime | None = None
        previous_sequence: int | None = None

        for path, trace in ordered:

            sequence = trace["sequence"]

            if sequence in by_sequence:
                errors.append(
                    f"{path.name}: duplicate Trace "
                    f"sequence {sequence} for "
                    f"Derivative {derivative_id}; "
                    f"already used by "
                    f"{by_sequence[sequence].name}"
                )
            else:
                by_sequence[sequence] = path

            current_time = parse_datetime(
                trace["timestamp"]
            )

            if (
                previous_time is not None
                and previous_sequence is not None
                and sequence > previous_sequence
                and current_time < previous_time
            ):
                errors.append(
                    f"{path.name}: Trace timestamp "
                    "order contradicts sequence order "
                    f"for Derivative {derivative_id}"
                )

            if (
                previous_sequence is None
                or sequence > previous_sequence
            ):
                previous_sequence = sequence
                previous_time = current_time

    # ---------------------------------------------------------
    # CVCP-03 / CVCP-04 / CVCP-05 / CVCP-11
    # Audit evidence and contribution integrity
    # ---------------------------------------------------------

    for audit_id, (path, audit) in audits.items():

        derivative_id = audit["derivative_id"]

        derivative_entry = derivatives.get(
            derivative_id
        )

        if derivative_entry is None:
            errors.append(
                f"{path.name}: Audit {audit_id} "
                f"references unknown Derivative "
                f"{derivative_id}"
            )

            derivative_origin_refs: set[str] = set()

        else:
            _, derivative = derivative_entry

            derivative_origin_refs = set(
                derivative.get(
                    "origin_refs",
                    [],
                )
            )

        audit_trace_refs = set(
            audit.get(
                "trace_refs",
                [],
            )
        )

        for trace_id in audit_trace_refs:

            trace_entry = traces.get(trace_id)

            if trace_entry is None:
                errors.append(
                    f"{path.name}: Audit {audit_id} "
                    f"references unknown Trace "
                    f"{trace_id}"
                )
                continue

            _, trace = trace_entry

            if trace["derivative_id"] != derivative_id:
                errors.append(
                    f"{path.name}: Trace {trace_id} "
                    f"belongs to "
                    f"{trace['derivative_id']}, "
                    "not audited Derivative "
                    f"{derivative_id}"
                )

        contributions = audit.get(
            "contributions",
            [],
        )

        contribution_origins: set[str] = set()

        for contribution in contributions:

            origin_id = contribution["origin_id"]

            if origin_id in contribution_origins:
                errors.append(
                    f"{path.name}: Audit {audit_id} "
                    "contains duplicate contribution "
                    f"Origin {origin_id}"
                )

            contribution_origins.add(origin_id)

            if origin_id not in derivative_origin_refs:
                errors.append(
                    f"{path.name}: contribution "
                    f"Origin {origin_id} is not "
                    "declared by Derivative "
                    f"{derivative_id}"
                )

            for trace_id in contribution[
                "evidence_trace_ids"
            ]:

                if trace_id not in audit_trace_refs:
                    errors.append(
                        f"{path.name}: contribution "
                        f"evidence Trace {trace_id} "
                        "is not listed in Audit "
                        "trace_refs"
                    )

                if trace_id not in traces:
                    errors.append(
                        f"{path.name}: contribution "
                        "evidence references unknown "
                        f"Trace {trace_id}"
                    )

        if audit["status"] == "verified":

            weight_sum = sum(
                float(contribution["weight"])
                for contribution in contributions
            )

            if not math.isclose(
                weight_sum,
                1.0,
                rel_tol=EPSILON,
                abs_tol=EPSILON,
            ):
                errors.append(
                    f"{path.name}: verified Audit "
                    f"{audit_id} contribution weights "
                    f"sum to {weight_sum:.12g}, "
                    "expected 1.0"
                )

    # ---------------------------------------------------------
    # CVCP-06 / CVCP-09 / CVCP-10 / CVCP-12
    # Royalty integrity
    # ---------------------------------------------------------

    for royalty_id, (path, royalty) in (
        royalties.items()
    ):

        audit_id = royalty["audit_id"]

        audit_entry = audits.get(audit_id)

        if audit_entry is None:
            errors.append(
                f"{path.name}: Royalty "
                f"{royalty_id} references unknown "
                f"Audit {audit_id}"
            )
            continue

        _, audit = audit_entry

        if audit["status"] != "verified":
            errors.append(
                f"{path.name}: Royalty "
                f"{royalty_id} references Audit "
                f"{audit_id} with status "
                f"{audit['status']!r}; "
                "a verified Audit is required"
            )

        audited_weights = {
            contribution["origin_id"]:
                float(contribution["weight"])
            for contribution
            in audit.get(
                "contributions",
                [],
            )
        }

        allocation_origins: set[str] = set()

        for allocation in royalty.get(
            "allocations",
            [],
        ):

            origin_id = allocation["origin_id"]

            if origin_id in allocation_origins:
                errors.append(
                    f"{path.name}: Royalty "
                    f"{royalty_id} contains duplicate "
                    f"allocation Origin {origin_id}"
                )

            allocation_origins.add(origin_id)

            if origin_id not in audited_weights:
                errors.append(
                    f"{path.name}: Royalty allocation "
                    f"Origin {origin_id} does not "
                    f"exist in Audit {audit_id} "
                    "contributions"
                )
                continue

            audited_weight = audited_weights[
                origin_id
            ]

            allocation_weight = float(
                allocation["contribution_weight"]
            )

            if not math.isclose(
                allocation_weight,
                audited_weight,
                rel_tol=EPSILON,
                abs_tol=EPSILON,
            ):
                errors.append(
                    f"{path.name}: Royalty "
                    "contribution_weight "
                    f"{allocation_weight} does not "
                    "match audited weight "
                    f"{audited_weight} for {origin_id}"
                )

            expected_amount = (
                float(
                    royalty["value_generated"]
                )
                * allocation_weight
                * float(
                    allocation["royalty_rate"]
                )
            )

            actual_amount = float(
                allocation["amount"]
            )

            if not math.isclose(
                actual_amount,
                expected_amount,
                rel_tol=EPSILON,
                abs_tol=EPSILON,
            ):
                errors.append(
                    f"{path.name}: Royalty amount "
                    f"{actual_amount} for {origin_id} "
                    "does not match expected "
                    f"{expected_amount}"
                )

            origin_entry = origins.get(origin_id)

            if origin_entry is not None:

                _, origin = origin_entry

                policy = origin["access_policy"]

                if (
                    policy.get("royalty_required")
                    and "royalty_rate" in policy
                ):

                    policy_rate = float(
                        policy["royalty_rate"]
                    )

                    allocation_rate = float(
                        allocation["royalty_rate"]
                    )

                    if not math.isclose(
                        allocation_rate,
                        policy_rate,
                        rel_tol=EPSILON,
                        abs_tol=EPSILON,
                    ):
                        errors.append(
                            f"{path.name}: Royalty rate "
                            f"{allocation_rate} does not "
                            "match Origin policy rate "
                            f"{policy_rate} for "
                            f"{origin_id}"
                        )

    # ---------------------------------------------------------
    # Value Cycle referential integrity
    # ---------------------------------------------------------

    for cycle_id, (path, cycle) in (
        index["value_cycle_record"].items()
    ):

        cycle_origins = set(
            cycle.get(
                "origin_refs",
                [],
            )
        )

        for origin_id in cycle_origins:

            if origin_id not in origins:
                errors.append(
                    f"{path.name}: Value Cycle "
                    f"{cycle_id} references unknown "
                    f"Origin {origin_id}"
                )

        derivative_id = cycle.get(
            "derivative_ref"
        )

        derivative = None

        if derivative_id is not None:

            derivative_entry = derivatives.get(
                derivative_id
            )

            if derivative_entry is None:
                errors.append(
                    f"{path.name}: Value Cycle "
                    f"{cycle_id} references unknown "
                    f"Derivative {derivative_id}"
                )

            else:
                _, derivative = derivative_entry

                derivative_origins = set(
                    derivative.get(
                        "origin_refs",
                        [],
                    )
                )

                if cycle_origins != derivative_origins:
                    errors.append(
                        f"{path.name}: Value Cycle "
                        "Origin set does not match "
                        f"Derivative {derivative_id} "
                        "Origin set"
                    )

        for trace_id in cycle.get(
            "trace_refs",
            [],
        ):

            trace_entry = traces.get(trace_id)

            if trace_entry is None:
                errors.append(
                    f"{path.name}: Value Cycle "
                    f"{cycle_id} references unknown "
                    f"Trace {trace_id}"
                )
                continue

            if derivative_id is not None:
                _, trace = trace_entry

                if (
                    trace["derivative_id"]
                    != derivative_id
                ):
                    errors.append(
                        f"{path.name}: Value Cycle "
                        f"Trace {trace_id} does not "
                        "belong to Derivative "
                        f"{derivative_id}"
                    )

        audit_id = cycle.get("audit_ref")
        audit = None

        if audit_id is not None:

            audit_entry = audits.get(audit_id)

            if audit_entry is None:
                errors.append(
                    f"{path.name}: Value Cycle "
                    f"{cycle_id} references unknown "
                    f"Audit {audit_id}"
                )

            else:
                _, audit = audit_entry

                if (
                    derivative_id is not None
                    and audit["derivative_id"]
                    != derivative_id
                ):
                    errors.append(
                        f"{path.name}: Value Cycle "
                        f"Audit {audit_id} does not "
                        "audit Derivative "
                        f"{derivative_id}"
                    )

        royalty_id = cycle.get(
            "royalty_ref"
        )

        royalty = None

        if royalty_id is not None:

            royalty_entry = royalties.get(
                royalty_id
            )

            if royalty_entry is None:
                errors.append(
                    f"{path.name}: Value Cycle "
                    f"{cycle_id} references unknown "
                    f"Royalty {royalty_id}"
                )

            else:
                _, royalty = royalty_entry

                if (
                    audit_id is not None
                    and royalty["audit_id"]
                    != audit_id
                ):
                    errors.append(
                        f"{path.name}: Value Cycle "
                        f"Royalty {royalty_id} does "
                        "not derive from Audit "
                        f"{audit_id}"
                    )

        status = cycle["cycle_status"]

        if status in {
            "audit_verified",
            "royalty_calculated",
            "settlement_pending",
            "settled",
        }:
            if (
                audit is not None
                and audit["status"] != "verified"
            ):
                errors.append(
                    f"{path.name}: Value Cycle "
                    f"status {status!r} requires "
                    "a verified Audit"
                )

        if (
            status == "settlement_pending"
            and royalty is not None
        ):
            if royalty[
                "settlement_status"
            ] not in {
                "pending",
                "processing",
            }:
                errors.append(
                    f"{path.name}: "
                    "settlement_pending cycle "
                    "requires Royalty status "
                    "'pending' or 'processing'"
                )

        if (
            status == "settled"
            and royalty is not None
        ):
            if (
                royalty["settlement_status"]
                != "settled"
            ):
                errors.append(
                    f"{path.name}: settled cycle "
                    "requires settled Royalty"
                )

        created_at = parse_datetime(
            cycle["created_at"]
        )

        updated_at = parse_datetime(
            cycle["updated_at"]
        )

        if updated_at < created_at:
            errors.append(
                f"{path.name}: updated_at "
                "precedes created_at"
            )

    return errors


def print_schema_errors(
    errors: list[str],
    indent: str = "  ",
) -> None:

    for error in errors:
        print(f"{indent}- {error}")


def main() -> int:

    print(
        "=== Civilization Value Cycle "
        "Protocol v0.1 Validation ==="
    )

    try:
        validators = load_schemas()

    except Exception as exc:
        print(
            "[fatal] schema loading failed: "
            f"{exc}"
        )
        return 2

    for record_type, path in (
        SCHEMA_FILES.items()
    ):
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
            "[fatal] no pass examples found"
        )
        return 2

    if not fail_paths:
        print(
            "[fatal] no fail examples found"
        )
        return 2

    print("\n[pass examples]\n")

    pass_records: list[
        tuple[Path, dict[str, Any]]
    ] = []

    unexpected = 0

    for path in pass_paths:

        print(
            f"- {path.relative_to(ROOT)}"
        )

        try:
            document = load_data(path)

        except ValidationFailure as exc:
            print(
                f"[parse-error] {exc}\n"
            )
            unexpected += 1
            continue

        errors = schema_errors(
            document,
            validators,
        )

        if errors:
            print("[schema-error]")
            print_schema_errors(errors)
            print()

            unexpected += 1
            continue

        print("[schema-ok]")

        pass_records.append(
            (path, document)
        )

        print()

    pass_semantic_errors = semantic_errors(
        pass_records
    )

    if pass_semantic_errors:

        print(
            "[pass semantic errors]"
        )

        print_schema_errors(
            pass_semantic_errors
        )

        unexpected += len(
            pass_semantic_errors
        )

    else:
        print(
            "[semantic-ok] "
            "pass example set\n"
        )

    print("[fail examples]\n")

    expected_failures = 0

    for path in fail_paths:

        print(
            f"- {path.relative_to(ROOT)}"
        )

        try:
            document = load_data(path)

        except ValidationFailure as exc:
            print(
                "[expected-parse-failure] "
                f"{exc}\n"
            )

            expected_failures += 1
            continue

        errors = schema_errors(
            document,
            validators,
        )

        if errors:

            print(
                "[expected-schema-failure]"
            )

            print_schema_errors(errors)
            print()

            expected_failures += 1
            continue

        print("[schema-ok]")

        scenario = (
            pass_records
            + [(path, document)]
        )

        errors = semantic_errors(
            scenario
        )

        if errors:

            print(
                "[expected-semantic-failure]"
            )

            print_schema_errors(errors)
            print()

            expected_failures += 1

        else:
            print(
                "[unexpected-pass]\n"
            )

            unexpected += 1

    print("=== Summary ===")

    print(
        f"pass examples: "
        f"{len(pass_paths)}"
    )

    print(
        f"fail examples: "
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
    sys.exit(main())
