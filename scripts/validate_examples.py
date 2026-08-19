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
    "audit_record": "audit_id",
    "royalty_record": "royalty_id",
    "state_transition_record": "transition_id",
    "value_cycle_record": "cycle_id",
}


LEGAL_TRANSITIONS = {
    ("origin_registered", "derivative_created"),
    ("derivative_created", "trace_recorded"),
    ("trace_recorded", "audit_pending"),
    ("audit_pending", "audit_verified"),
    ("audit_pending", "disputed"),
    ("disputed", "audit_pending"),
    ("audit_verified", "royalty_calculated"),
    ("royalty_calculated", "settlement_pending"),
    ("settlement_pending", "settled"),
    ("settlement_pending", "disputed"),
    ("disputed", "settlement_pending"),
}


EPSILON = 1e-9


class ValidationFailure(Exception):
    pass


def load_document(path: Path) -> dict[str, Any]:
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


def expand_fixture(
    document: dict[str, Any],
) -> list[dict[str, Any]]:

    if document.get("fixture_type") != "semantic_scenario":
        return [document]

    records = document.get("records")

    if not isinstance(records, list) or not records:
        raise ValidationFailure(
            "semantic_scenario requires a non-empty records array"
        )

    if not all(isinstance(record, dict) for record in records):
        raise ValidationFailure(
            "every semantic_scenario record must be an object"
        )

    return records


def example_files(directory: Path) -> list[Path]:
    paths: list[Path] = []

    for suffix in ("*.yaml", "*.yml", "*.json"):
        paths.extend(directory.glob(suffix))

    return sorted(
        set(paths),
        key=lambda path: path.name,
    )


def load_schemas() -> dict[str, Draft202012Validator]:
    validators: dict[str, Draft202012Validator] = {}

    for record_type, path in SCHEMA_FILES.items():
        schema = load_document(path)

        Draft202012Validator.check_schema(schema)

        validators[record_type] = Draft202012Validator(
            schema,
            format_checker=FormatChecker(),
        )

    return validators


def schema_errors(
    record: dict[str, Any],
    validators: dict[str, Draft202012Validator],
) -> list[str]:

    record_type = record.get("record_type")

    if record_type not in validators:
        return [
            f"unknown or missing record_type: {record_type!r}"
        ]

    errors = sorted(
        validators[record_type].iter_errors(record),
        key=lambda error: str(list(error.absolute_path)),
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


def parse_datetime(value: str) -> datetime:
    if value.endswith("Z"):
        value = value[:-1] + "+00:00"

    return datetime.fromisoformat(value)


def build_index(
    records: list[dict[str, Any]],
) -> tuple[
    dict[str, dict[str, dict[str, Any]]],
    list[str],
]:

    index = {
        record_type: {}
        for record_type in ID_FIELDS
    }

    errors: list[str] = []

    for record in records:
        record_type = record.get("record_type")
        id_field = ID_FIELDS.get(record_type)

        if id_field is None:
            continue

        record_id = record.get(id_field)

        if not isinstance(record_id, str):
            continue

        if record_id in index[record_type]:
            errors.append(
                f"duplicate {id_field}: {record_id}"
            )
            continue

        index[record_type][record_id] = record

    return index, errors


def trace_parents(
    trace: dict[str, Any],
) -> set[str]:

    parents: set[str] = set()

    previous = trace.get("previous_trace_id")

    if isinstance(previous, str):
        parents.add(previous)

    for parent in trace.get("causal_parent_refs", []):
        parents.add(parent)

    return parents


def semantic_errors(
    records: list[dict[str, Any]],
) -> list[str]:

    index, errors = build_index(records)

    origins = index["origin_record"]
    derivatives = index["derivative_record"]
    traces = index["trace_record"]
    chains = index["trace_chain_record"]
    audits = index["audit_record"]
    royalties = index["royalty_record"]
    transitions = index["state_transition_record"]
    cycles = index["value_cycle_record"]

    # ------------------------------------------------------
    # Origin / Derivative integrity
    # ------------------------------------------------------

    for derivative_id, derivative in derivatives.items():

        compliance = {
            item["origin_id"]: item
            for item in derivative.get(
                "policy_compliance",
                [],
            )
            if isinstance(item, dict)
            and isinstance(item.get("origin_id"), str)
        }

        for origin_id in derivative.get("origin_refs", []):

            origin = origins.get(origin_id)

            if origin is None:
                errors.append(
                    f"{derivative_id}: "
                    f"unknown Origin {origin_id}"
                )
                continue

            policy = origin["access_policy"]

            if policy["reference"] == "deny":
                errors.append(
                    f"{derivative_id}: "
                    f"Origin {origin_id} denies reference"
                )

            if policy["reference"] == "conditional":
                check = compliance.get(origin_id)

                if (
                    check is None
                    or check.get("status") != "satisfied"
                ):
                    errors.append(
                        f"{derivative_id}: "
                        f"conditional Origin {origin_id} "
                        "requires satisfied policy_compliance"
                    )

    # ------------------------------------------------------
    # Trace parent integrity
    # CVCP-14 / 15 / 17 / 18
    # ------------------------------------------------------

    for trace_id, trace in traces.items():

        derivative_id = trace["derivative_id"]

        if derivative_id not in derivatives:
            errors.append(
                f"{trace_id}: "
                f"unknown Derivative {derivative_id}"
            )

        for parent_id in trace_parents(trace):

            parent = traces.get(parent_id)

            if parent is None:
                errors.append(
                    f"{trace_id}: "
                    f"unknown parent Trace {parent_id}"
                )
                continue

            if parent["derivative_id"] != derivative_id:
                errors.append(
                    f"{trace_id}: "
                    f"cross-Derivative parent {parent_id}"
                )

            if parent["sequence"] >= trace["sequence"]:
                errors.append(
                    f"{trace_id}: "
                    f"parent precedence violated by {parent_id}"
                )

            if (
                parse_datetime(parent["timestamp"])
                > parse_datetime(trace["timestamp"])
            ):
                errors.append(
                    f"{trace_id}: "
                    f"parent timestamp occurs after child "
                    f"{parent_id}"
                )

    # ------------------------------------------------------
    # Trace Chain DAG integrity
    # CVCP-13 / 16 / 19 / 20
    # ------------------------------------------------------

    for chain_id, chain in chains.items():

        refs = chain["trace_refs"]
        ref_set = set(refs)

        if chain["event_count"] != len(refs):
            errors.append(
                f"{chain_id}: event_count mismatch: "
                f"{chain['event_count']} != {len(refs)}"
            )

        if chain["root_trace_id"] not in ref_set:
            errors.append(
                f"{chain_id}: root_trace_id is not in trace_refs"
            )

        if not set(chain["terminal_trace_ids"]).issubset(ref_set):
            errors.append(
                f"{chain_id}: terminal Trace outside trace_refs"
            )

        nodes: dict[str, dict[str, Any]] = {}

        for trace_id in refs:

            trace = traces.get(trace_id)

            if trace is None:
                errors.append(
                    f"{chain_id}: unknown Trace {trace_id}"
                )
                continue

            nodes[trace_id] = trace

            if (
                trace["derivative_id"]
                != chain["derivative_id"]
            ):
                errors.append(
                    f"{chain_id}: Trace {trace_id} "
                    "belongs to another Derivative"
                )

        children = {
            trace_id: set()
            for trace_id in nodes
        }

        roots: list[str] = []

        for trace_id, trace in nodes.items():

            parents = trace_parents(trace)

            in_chain = {
                parent
                for parent in parents
                if parent in nodes
            }

            outside_chain = parents - in_chain

            if outside_chain:
                errors.append(
                    f"{chain_id}: Trace {trace_id} "
                    "parent(s) outside chain: "
                    f"{sorted(outside_chain)}"
                )

            if not in_chain:
                roots.append(trace_id)

            for parent in in_chain:
                children[parent].add(trace_id)

        expected_root = chain["root_trace_id"]

        if set(roots) != {expected_root}:
            errors.append(
                f"{chain_id}: roots {sorted(roots)} "
                f"do not equal declared root {expected_root}"
            )

        # Kahn's algorithm: cycle detection
        indegree = {
            trace_id: 0
            for trace_id in nodes
        }

        for child_set in children.values():
            for child in child_set:
                indegree[child] += 1

        queue = deque(
            trace_id
            for trace_id, degree in indegree.items()
            if degree == 0
        )

        visited: list[str] = []

        while queue:
            current = queue.popleft()
            visited.append(current)

            for child in children[current]:
                indegree[child] -= 1

                if indegree[child] == 0:
                    queue.append(child)

        if len(visited) != len(nodes):
            errors.append(
                f"{chain_id}: causal cycle detected"
            )

        # Reachability from declared root
        reachable: set[str] = set()

        if expected_root in nodes:

            queue = deque([expected_root])

            while queue:
                current = queue.popleft()

                if current in reachable:
                    continue

                reachable.add(current)

                for child in children[current]:
                    queue.append(child)

            unreachable = set(nodes) - reachable

            if unreachable:
                errors.append(
                    f"{chain_id}: orphan/unreachable Trace(s): "
                    f"{sorted(unreachable)}"
                )

        actual_terminals = {
            trace_id
            for trace_id, child_set in children.items()
            if not child_set
        }

        declared_terminals = set(
            chain["terminal_trace_ids"]
        )

        if actual_terminals != declared_terminals:
            errors.append(
                f"{chain_id}: terminal mismatch: "
                f"actual={sorted(actual_terminals)}, "
                f"declared={sorted(declared_terminals)}"
            )

    # ------------------------------------------------------
    # Audit integrity
    # ------------------------------------------------------

    for audit_id, audit in audits.items():

        derivative_id = audit["derivative_id"]

        derivative = derivatives.get(derivative_id)

        if derivative is None:
            errors.append(
                f"{audit_id}: "
                f"unknown Derivative {derivative_id}"
            )

        chain = chains.get(audit["trace_chain_ref"])

        if chain is None:
            errors.append(
                f"{audit_id}: "
                f"unknown Trace Chain "
                f"{audit['trace_chain_ref']}"
            )

        else:
            if chain["derivative_id"] != derivative_id:
                errors.append(
                    f"{audit_id}: Trace Chain "
                    "Derivative mismatch"
                )

            if not set(audit["trace_refs"]).issubset(
                set(chain["trace_refs"])
            ):
                errors.append(
                    f"{audit_id}: Audit references "
                    "Trace outside Trace Chain"
                )

        derivative_origins = set()

        if derivative is not None:
            derivative_origins = set(
                derivative["origin_refs"]
            )

        audit_trace_refs = set(audit["trace_refs"])

        seen_origins: set[str] = set()

        for contribution in audit["contributions"]:

            origin_id = contribution["origin_id"]

            if origin_id in seen_origins:
                errors.append(
                    f"{audit_id}: duplicate contribution "
                    f"Origin {origin_id}"
                )

            seen_origins.add(origin_id)

            if origin_id not in derivative_origins:
                errors.append(
                    f"{audit_id}: contribution Origin "
                    f"{origin_id} is not declared "
                    "by the Derivative"
                )

            for trace_id in contribution[
                "evidence_trace_ids"
            ]:
                if trace_id not in audit_trace_refs:
                    errors.append(
                        f"{audit_id}: evidence Trace "
                        f"{trace_id} is outside Audit trace_refs"
                    )

                if trace_id not in traces:
                    errors.append(
                        f"{audit_id}: unknown evidence "
                        f"Trace {trace_id}"
                    )

        if audit["status"] == "verified":

            weight_sum = sum(
                float(item["weight"])
                for item in audit["contributions"]
            )

            if not math.isclose(
                weight_sum,
                1.0,
                rel_tol=EPSILON,
                abs_tol=EPSILON,
            ):
                errors.append(
                    f"{audit_id}: verified contribution "
                    f"weights sum to {weight_sum}, expected 1.0"
                )

    # ------------------------------------------------------
    # Royalty integrity
    # ------------------------------------------------------

    for royalty_id, royalty in royalties.items():

        audit = audits.get(royalty["audit_id"])

        if audit is None:
            errors.append(
                f"{royalty_id}: "
                f"unknown Audit {royalty['audit_id']}"
            )
            continue

        if audit["status"] != "verified":
            errors.append(
                f"{royalty_id}: Royalty requires "
                "a verified Audit"
            )

        audited_weights = {
            item["origin_id"]: float(item["weight"])
            for item in audit["contributions"]
        }

        seen_origins: set[str] = set()

        for allocation in royalty["allocations"]:

            origin_id = allocation["origin_id"]

            if origin_id in seen_origins:
                errors.append(
                    f"{royalty_id}: duplicate Royalty "
                    f"Origin {origin_id}"
                )

            seen_origins.add(origin_id)

            audited_weight = audited_weights.get(origin_id)

            if audited_weight is None:
                errors.append(
                    f"{royalty_id}: allocation Origin "
                    f"{origin_id} was not audited"
                )
                continue

            actual_weight = float(
                allocation["contribution_weight"]
            )

            if not math.isclose(
                actual_weight,
                audited_weight,
                rel_tol=EPSILON,
                abs_tol=EPSILON,
            ):
                errors.append(
                    f"{royalty_id}: contribution weight "
                    f"does not match Audit for {origin_id}"
                )

            expected_amount = (
                float(royalty["value_generated"])
                * actual_weight
                * float(allocation["royalty_rate"])
            )

            actual_amount = float(allocation["amount"])

            if not math.isclose(
                expected_amount,
                actual_amount,
                rel_tol=EPSILON,
                abs_tol=EPSILON,
            ):
                errors.append(
                    f"{royalty_id}: amount mismatch "
                    f"for {origin_id}: "
                    f"{actual_amount} != {expected_amount}"
                )

            origin = origins.get(origin_id)

            if origin is not None:

                policy = origin["access_policy"]

                if (
                    policy.get("royalty_required")
                    and "royalty_rate" in policy
                ):
                    expected_rate = float(
                        policy["royalty_rate"]
                    )

                    actual_rate = float(
                        allocation["royalty_rate"]
                    )

                    if not math.isclose(
                        expected_rate,
                        actual_rate,
                        rel_tol=EPSILON,
                        abs_tol=EPSILON,
                    ):
                        errors.append(
                            f"{royalty_id}: royalty rate "
                            f"does not match Origin policy "
                            f"for {origin_id}"
                        )

    # ------------------------------------------------------
    # State Transition legality
    # CVCP-21 / CVCP-25
    # ------------------------------------------------------

    for transition_id, transition in transitions.items():

        pair = (
            transition["previous_status"],
            transition["next_status"],
        )

        if pair not in LEGAL_TRANSITIONS:
            errors.append(
                f"{transition_id}: illegal transition "
                f"{pair[0]} -> {pair[1]}"
            )
            continue

        cycle = cycles.get(transition["cycle_id"])

        if cycle is None:
            errors.append(
                f"{transition_id}: unknown Value Cycle "
                f"{transition['cycle_id']}"
            )
            continue

        evidence = set(transition["evidence_refs"])
        next_status = transition["next_status"]

        required_ref: str | None = None

        if next_status == "derivative_created":
            required_ref = cycle.get("derivative_ref")

        elif next_status in {
            "trace_recorded",
            "audit_pending",
        }:
            required_ref = cycle.get("trace_chain_ref")

        elif next_status == "audit_verified":
            required_ref = cycle.get("audit_ref")

        elif next_status in {
            "royalty_calculated",
            "settlement_pending",
        }:
            required_ref = cycle.get("royalty_ref")

        elif next_status == "settled":

            royalty_id = cycle.get("royalty_ref")

            royalty = (
                royalties.get(royalty_id)
                if isinstance(royalty_id, str)
                else None
            )

            if royalty is None:
                errors.append(
                    f"{transition_id}: settled transition "
                    "requires Royalty Record"
                )
            else:
                settlement_ref = royalty.get(
                    "settlement_ref"
                )

                if not settlement_ref:
                    errors.append(
                        f"{transition_id}: settled transition "
                        "requires settlement_ref"
                    )
                elif settlement_ref not in evidence:
                    errors.append(
                        f"{transition_id}: settlement_ref "
                        "missing from evidence_refs"
                    )

        if (
            required_ref is not None
            and required_ref not in evidence
        ):
            errors.append(
                f"{transition_id}: required evidence "
                f"{required_ref} is missing"
            )

    # ------------------------------------------------------
    # Value Cycle integrity
    # CVCP-22 / 23 / 24
    # ------------------------------------------------------

    for cycle_id, cycle in cycles.items():

        created_at = parse_datetime(
            cycle["created_at"]
        )

        updated_at = parse_datetime(
            cycle["updated_at"]
        )

        if updated_at < created_at:
            errors.append(
                f"{cycle_id}: updated_at precedes created_at"
            )

        for origin_id in cycle["origin_refs"]:
            if origin_id not in origins:
                errors.append(
                    f"{cycle_id}: unknown Origin {origin_id}"
                )

        derivative_id = cycle.get("derivative_ref")

        derivative = (
            derivatives.get(derivative_id)
            if isinstance(derivative_id, str)
            else None
        )

        if (
            derivative_id is not None
            and derivative is None
        ):
            errors.append(
                f"{cycle_id}: "
                f"unknown Derivative {derivative_id}"
            )

        if derivative is not None:

            if set(cycle["origin_refs"]) != set(
                derivative["origin_refs"]
            ):
                errors.append(
                    f"{cycle_id}: Origin set does not "
                    "match Derivative Origin set"
                )

        chain_id = cycle.get("trace_chain_ref")

        chain = (
            chains.get(chain_id)
            if isinstance(chain_id, str)
            else None
        )

        if chain_id is not None and chain is None:
            errors.append(
                f"{cycle_id}: "
                f"unknown Trace Chain {chain_id}"
            )

        if chain is not None:

            if (
                derivative_id is not None
                and chain["derivative_id"] != derivative_id
            ):
                errors.append(
                    f"{cycle_id}: Trace Chain "
                    "Derivative mismatch"
                )

            if set(cycle.get("trace_refs", [])) != set(
                chain["trace_refs"]
            ):
                errors.append(
                    f"{cycle_id}: cycle Trace set "
                    "does not equal Trace Chain set"
                )

        audit_id = cycle.get("audit_ref")

        audit = (
            audits.get(audit_id)
            if isinstance(audit_id, str)
            else None
        )

        if audit_id is not None and audit is None:
            errors.append(
                f"{cycle_id}: unknown Audit {audit_id}"
            )

        if (
            audit is not None
            and derivative_id is not None
            and audit["derivative_id"] != derivative_id
        ):
            errors.append(
                f"{cycle_id}: Audit Derivative mismatch"
            )

        royalty_id = cycle.get("royalty_ref")

        royalty = (
            royalties.get(royalty_id)
            if isinstance(royalty_id, str)
            else None
        )

        if royalty_id is not None and royalty is None:
            errors.append(
                f"{cycle_id}: unknown Royalty {royalty_id}"
            )

        if (
            royalty is not None
            and audit_id is not None
            and royalty["audit_id"] != audit_id
        ):
            errors.append(
                f"{cycle_id}: Royalty does not derive "
                "from cycle Audit"
            )

        transition_sequence: list[
            dict[str, Any]
        ] = []

        for transition_id in cycle.get(
            "transition_refs",
            [],
        ):

            transition = transitions.get(transition_id)

            if transition is None:
                errors.append(
                    f"{cycle_id}: unknown State Transition "
                    f"{transition_id}"
                )
                continue

            if transition["cycle_id"] != cycle_id:
                errors.append(
                    f"{cycle_id}: State Transition "
                    f"{transition_id} belongs to "
                    "another Value Cycle"
                )

            transition_sequence.append(transition)

        for previous, current in zip(
            transition_sequence,
            transition_sequence[1:],
        ):

            if (
                previous["next_status"]
                != current["previous_status"]
            ):
                errors.append(
                    f"{cycle_id}: broken transition "
                    f"continuity "
                    f"{previous['transition_id']} -> "
                    f"{current['transition_id']}"
                )

            if (
                parse_datetime(previous["transitioned_at"])
                > parse_datetime(current["transitioned_at"])
            ):
                errors.append(
                    f"{cycle_id}: transition timestamp "
                    "order violation"
                )

        if transition_sequence:

            latest_status = transition_sequence[-1][
                "next_status"
            ]

            if latest_status != cycle["cycle_status"]:
                errors.append(
                    f"{cycle_id}: cycle_status mismatch: "
                    f"latest={latest_status}, "
                    f"current={cycle['cycle_status']}"
                )

    return errors


def main() -> int:

    print(
        "=== Civilization Value Cycle "
        "Protocol v0.2 Validation ==="
    )

    try:
        validators = load_schemas()

    except Exception as exc:
        print(
            f"[fatal] schema loading failed: {exc}"
        )
        return 2

    for record_type, path in SCHEMA_FILES.items():
        print(
            f"schema [{record_type}]: "
            f"{path.relative_to(ROOT)}"
        )

    pass_paths = example_files(PASS_DIR)
    fail_paths = example_files(FAIL_DIR)

    if not pass_paths:
        print("[fatal] no pass examples found")
        return 2

    if not fail_paths:
        print("[fatal] no fail examples found")
        return 2

    unexpected = 0
    pass_records: list[dict[str, Any]] = []

    print("\n[pass examples]\n")

    for path in pass_paths:

        print(f"- {path.relative_to(ROOT)}")

        try:
            document = load_document(path)
            records = expand_fixture(document)

        except ValidationFailure as exc:
            print(f"[parse-error] {exc}\n")
            unexpected += 1
            continue

        file_failed = False

        for record in records:

            errors = schema_errors(
                record,
                validators,
            )

            if errors:
                print("[schema-error]")

                for error in errors:
                    print(f"  - {error}")

                file_failed = True

        if file_failed:
            unexpected += 1
            print()
            continue

        print("[schema-ok]")

        pass_records.extend(records)

        print()

    pass_semantic = semantic_errors(
        pass_records
    )

    if pass_semantic:
        print("[pass semantic errors]")

        for error in pass_semantic:
            print(f"  - {error}")

        unexpected += len(pass_semantic)

    else:
        print("[semantic-ok] pass example set\n")

    print("[fail examples]\n")

    expected_failures = 0

    for path in fail_paths:

        print(f"- {path.relative_to(ROOT)}")

        try:
            document = load_document(path)
            records = expand_fixture(document)

        except ValidationFailure as exc:
            print(
                f"[expected-parse-failure] {exc}\n"
            )
            expected_failures += 1
            continue

        all_schema_errors: list[str] = []

        for record in records:
            all_schema_errors.extend(
                schema_errors(
                    record,
                    validators,
                )
            )

        if all_schema_errors:

            print("[expected-schema-failure]")

            for error in all_schema_errors:
                print(f"  - {error}")

            print()

            expected_failures += 1
            continue

        print("[schema-ok]")

        scenario_records = (
            pass_records
            + records
        )

        errors = semantic_errors(
            scenario_records
        )

        if errors:

            print("[expected-semantic-failure]")

            for error in errors:
                print(f"  - {error}")

            print()

            expected_failures += 1

        else:
            print("[unexpected-pass]\n")
            unexpected += 1

    print("=== Summary ===")

    print(
        f"pass example files: {len(pass_paths)}"
    )

    print(
        f"fail example files: {len(fail_paths)}"
    )

    print(
        "expected failures observed: "
        f"{expected_failures}"
    )

    print(
        f"unexpected results: {unexpected}"
    )

    if unexpected:
        print("[validation-failed]")
        return 1

    print("[validation-passed]")
    return 0


if __name__ == "__main__":
    sys.exit(main())


