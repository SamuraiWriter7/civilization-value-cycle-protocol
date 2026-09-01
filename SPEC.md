# Civilization Value Cycle Protocol (CVCP) — Specification v0.5

**Version:** 0.5.0
**Codename:** Reconciliation & Recovery
**Status:** Specification / Validated
**Protocol:** Civilization Value Cycle Protocol
**Abbreviation:** CVCP

---

## 1. Purpose

Civilization Value Cycle Protocol (CVCP) is a protocol specification for tracing value from its origin through derivation, evidence, contribution assessment, audit, royalty allocation, external settlement, dispute, reconciliation, and recovery.

CVCP does not attempt to decide legal ownership, execute payments, or replace external authorization systems.

Its purpose is to create a machine-readable and auditable structure through which value can be traced and corrected without erasing prior history.

The v0.5 core principle is:

> **A completed settlement must remain correctable without erasing its history.**

In other words:

```text
Value
  ↓
Trace
  ↓
Assessment
  ↓
Audit
  ↓
Allocation
  ↓
Settlement
  ↓
Correction
```

must remain reconstructable as one continuous causal history.

---

# 2. Scope

CVCP v0.5 defines records and semantic constraints for:

* Origin registration
* Derivative declaration
* Trace recording
* Trace-chain construction
* Evidence assessment
* Contribution assessment
* Audit
* Royalty calculation
* Settlement request generation
* External settlement receipt recording
* Dispute recording
* Reconciliation
* Supersession
* Recovery
* State transition
* Value-cycle finalization

CVCP deliberately separates:

```text
Evidence
from
Judgment

Royalty
from
Payment

Settlement Request
from
Settlement Execution

Historical Record
from
Corrected Record
```

---

# 3. Non-Goals

CVCP does not:

* hold private keys;
* store bank credentials;
* execute fiat or token transfers;
* act as a legal court;
* determine copyright ownership by itself;
* make an AI agent the final authority for settlement;
* erase incorrect historical records;
* overwrite prior audit or settlement history.

External systems remain responsible for actual authority and execution.

---

# 4. Core Architecture

The canonical v0.5 architecture is:

```text
Origin
  ↓
Derivative
  ↓
Trace
  ↓
Trace Chain
  ↓
Evidence Assessment
  ↓
Contribution Assessment
  ↓
Audit
  ↓
Royalty
  ↓
Settlement Request
  ║
  ║  Settlement Boundary
  ║
External Settlement Executor
  ║
  ↓
Settlement Receipt
  ↓
Dispute
  ↓
Reconciliation
  ↓
Correction / Recovery
  ↓
Value Cycle Finalization
```

The settlement boundary is explicit.

```text
CVCP
=
settlement metadata plane

External provider
=
money execution plane
```

---

# 5. Fundamental Principles

## 5.1 Origin Before Allocation

A Royalty allocation must ultimately be traceable to one or more registered Origins.

---

## 5.2 Trace Is Evidence; Audit Is Judgment

Trace records describe what occurred.

Audit records evaluate what those traces mean.

```text
Trace ≠ Audit
```

This separation prevents raw evidence from being silently converted into authoritative judgment.

---

## 5.3 Contribution Must Be Explainable

A contribution value must not be an unexplained number.

It must be derived from an explicit methodology and supporting Evidence Assessments.

> **Contribution must be explainable, not merely assigned.**

---

## 5.4 Royalty Is Not Payment

A Royalty record determines:

* who is attributed;
* how much contribution was recognized;
* what royalty rate applies;
* how much should be returned.

It does not prove that payment occurred.

```text
Royalty ≠ Payment
```

---

## 5.5 Settlement Requires External Execution

CVCP may authorize and describe settlement, but actual execution occurs through an external authority.

> **Settlement must be externally executed and independently receipted.**

---

## 5.6 Correction Must Be Append-Only

Historical records must not be silently rewritten.

```text
Incorrect old record
        ↓
Reconciliation
        ↓
New corrected record
```

The old record remains part of history.

> **Correction must create history, not destroy history.**

---

# 6. Record Types

CVCP v0.5 defines fourteen record types.

```text
schemas/
├── origin-record.schema.json
├── derivative-record.schema.json
├── trace-record.schema.json
├── trace-chain-record.schema.json
├── evidence-assessment-record.schema.json
├── contribution-assessment-record.schema.json
├── audit-record.schema.json
├── royalty-record.schema.json
├── settlement-request-record.schema.json
├── settlement-receipt-record.schema.json
├── dispute-record.schema.json
├── reconciliation-record.schema.json
├── state-transition-record.schema.json
└── value-cycle-record.schema.json
```

---

# 7. Origin Record

The Origin Record represents the root asset from which later value may derive.

Identifier:

```text
OID:<namespace>/<asset>/<version>/<revision>
```

Example:

```text
OID:book/shidenkai-ai/civilization-os/v1
```

An Origin contains:

* creator identity;
* asset identity;
* content hash;
* rights holders;
* license information;
* access policy;
* attribution requirements;
* royalty requirements;
* provenance references.

An Origin acts as the root of a causal value path.

---

# 8. Derivative Record

A Derivative Record declares that an output depends on one or more Origins.

Identifier:

```text
DID:<agent>/<task>/<timestamp>/<nonce>
```

A Derivative must explicitly declare its `origin_refs`.

Conditional Origin policies must be accompanied by satisfied policy-compliance evidence.

---

# 9. Trace Record

A Trace Record represents one causal event.

Supported event types include:

```text
reference
transform
reasoning
decision
action
result
```

Trace records form a causal graph rather than a simple log.

A Trace may contain:

```text
previous_trace_id
causal_parent_refs[]
```

CVCP prohibits causal cycles.

---

# 10. Trace Chain Record

A Trace Chain groups Trace Records belonging to one Derivative.

It defines:

* root Trace;
* terminal Traces;
* Trace membership;
* event count;
* chain hash.

A valid Trace Chain must form a connected DAG.

```text
             ┌─ transform ─┐
reference ───┤             ├─ result
             └─ reasoning ─┘
```

---

# 11. Evidence Assessment

Evidence Assessment evaluates how strongly Trace evidence supports an Origin's contribution.

It is intentionally separate from Contribution Assessment.

Conceptually:

```text
Evidence
  ↓
Contribution
  ↓
Confidence
```

Evidence existence does not automatically determine contribution magnitude.

---

# 12. Contribution Assessment

Contribution Assessment estimates relative contribution using an explicit methodology.

The baseline v0.5-compatible methodology retained from v0.3 is:

```yaml
methodology:
  method_id: cvcp-weighted-factor-v1
  version: "1.0"

  coefficients:
    reference_depth: 0.15
    transformation_dependency: 0.25
    reasoning_influence: 0.20
    decision_influence: 0.20
    outcome_influence: 0.20

  evidence_adjustment: multiplicative
```

The baseline calculation is:

```text
raw_score =
0.15 × reference_depth
+ 0.25 × transformation_dependency
+ 0.20 × reasoning_influence
+ 0.20 × decision_influence
+ 0.20 × outcome_influence
```

With multiplicative evidence adjustment:

```text
adjusted_score
=
raw_score × evidence_strength
```

Normalization:

```text
normalized_weight_i
=
adjusted_score_i
/
Σ adjusted_score_j
```

Normalized weights must sum to 1.

---

# 13. Audit Record

Audit transforms assessed evidence and contribution into an auditable judgment.

Audit status:

```text
verified
provisional
disputed
rejected
```

The standard confidence model is:

```text
base =
(
  evidence_quality
  + trace_completeness
  + contribution_stability
  + methodology_reliability
) / 4

confidence =
base × (1 - conflict_penalty)
```

The standard profile uses thresholds for:

```text
verified
provisional
rejected
```

v0.5 adds optional:

```text
supersedes_ref
```

so reassessment can create a new Audit without deleting the old one.

---

# 14. Royalty Record

Royalty records convert audited contribution into value allocation.

Conceptually:

```text
Value Generated
      ×
Contribution Weight
      ×
Royalty Rate
      =
Royalty Amount
```

A Royalty may reference:

```text
settlement_request_ref
settlement_receipt_refs[]
```

v0.5 also supports:

```text
supersedes_ref
```

for append-only recalculation.

---

# 15. Settlement Request

Settlement Request represents an authorized request for external execution.

Identifier:

```text
SRQID:<requester>/<timestamp>/<nonce>
```

A Settlement Request includes:

* Royalty reference;
* Audit reference;
* value unit;
* allocations;
* beneficiaries;
* destination references;
* authorization references;
* idempotency key;
* request status.

Execution authority is fixed as:

```text
external
```

CVCP stores references to authorization and destination systems rather than secrets.

---

# 16. Settlement Receipt

Settlement Receipt represents evidence returned from an external settlement executor.

Identifier:

```text
SRCID:<executor>/<timestamp>/<nonce>
```

Supported statuses include:

```text
processing
settled
failed
disputed
reversed
```

A settled Receipt must provide external transaction evidence.

A reversal is never implemented by deleting the original Receipt.

Instead:

```text
Original settled Receipt
        ↓
Reversal Receipt
        ↓
supersedes_ref
```

---

# 17. Dispute Record

v0.5 introduces `DisputeRecord`.

Identifier:

```text
DPID:<actor>/<timestamp>/<nonce>
```

A dispute identifies exactly what is disputed.

Supported subjects:

```text
origin
derivative
trace
contribution
audit
royalty
settlement_request
settlement_receipt
```

Typical dispute types include:

```text
ownership
attribution
contribution_weight
royalty_amount
beneficiary
settlement_amount
duplicate_settlement
missing_settlement
unauthorized_execution
evidence_integrity
other
```

Dispute status:

```text
open
under_review
accepted
rejected
resolved
```

A resolved dispute must reference a Reconciliation Record.

---

# 18. Reconciliation Record

v0.5 introduces `ReconciliationRecord`.

Identifier:

```text
RCID:<resolver>/<timestamp>/<nonce>
```

Reconciliation describes how an inconsistency, dispute, or failure was handled.

Resolution types:

```text
no_change
allocation_correction
beneficiary_correction
royalty_recalculation
settlement_retry
settlement_reversal
audit_reassessment
cycle_reopen
other
```

Resolution actions:

```text
retain
supersede
recalculate
retry
reverse
reissue
reassess
close
```

A Reconciliation explicitly separates:

```text
cause
affected records
actions
resulting records
authorization
result
```

---

# 19. Supersession

Supersession links a corrected record to the record it replaces operationally.

Supported v0.5 supersession families include:

```text
Audit → Audit
Royalty → Royalty
Settlement Request → Settlement Request
Settlement Receipt → Settlement Receipt
```

Example:

```text
RID:r001
   ↓
superseded by
   ↓
RID:r002
```

Supersession does not delete `r001`.

A valid supersession chain must be acyclic.

---

# 20. Recovery Depth

Not every error requires restarting the entire Value Cycle.

CVCP v0.5 supports recovery at different depths.

## Level 1 — Settlement Recovery

```text
Origin     valid
Trace      valid
Audit      valid
Royalty    valid
Settlement failed
```

Return to:

```text
settlement_pending
```

---

## Level 2 — Royalty Recovery

If calculation or allocation is wrong:

```text
Reconciliation
      ↓
New Royalty
      ↓
New Settlement
```

---

## Level 3 — Audit Recovery

If contribution or judgment must be reassessed:

```text
disputed
   ↓
reconciliation
   ↓
audit_pending
```

---

## Level 4 — Causal Recovery

If the problem reaches Origin or Trace integrity, recovery may return to the causal layer.

```text
Derivative
or
Trace
```

must then be reconstructed or reassessed.

---

# 21. State Model

CVCP v0.5 defines:

```text
origin_registered
derivative_created
trace_recorded
audit_pending
audit_provisional
audit_verified
royalty_calculated
settlement_pending
settlement_processing
settlement_failed
settled
disputed
reconciliation_pending
reconciliation_processing
reconciled
```

Canonical normal path:

```text
origin_registered
        ↓
derivative_created
        ↓
trace_recorded
        ↓
audit_pending
        ↓
audit_verified
        ↓
royalty_calculated
        ↓
settlement_pending
        ↓
settlement_processing
        ↓
settled
```

Canonical reconciliation path:

```text
settled
   ↓
disputed
   ↓
reconciliation_pending
   ↓
reconciliation_processing
   ↓
reconciled
```

A reconciled cycle may reopen at the minimum required depth.

---

# 22. v0.5 Invariants

CVCP v0.5 preserves all invariants established in v0.1 through v0.4.

The following invariants are added in v0.5.

## CVCP-59 — Explicit Dispute Subject

Every Dispute must identify:

```text
subject_type
subject_ref
```

---

## CVCP-60 — Dispute Evidence Requirement

Every Dispute must provide at least one evidence reference.

---

## CVCP-61 — Existing Subject Requirement

A Dispute subject must resolve to an existing CVCP Record of the declared type.

---

## CVCP-62 — No Silent Mutation

A correction must not silently overwrite an existing historical Record.

---

## CVCP-63 — Reconciliation Requires Cause

A Reconciliation must contain at least one:

```text
dispute_ref
```

or:

```text
cause_ref
```

---

## CVCP-64 — Resolution Traceability

Affected Records must be explicitly identified.

---

## CVCP-65 — Result Traceability

Records created by reconciliation must appear in:

```text
resulting_record_refs
```

---

## CVCP-66 — Authorization Required for Value Mutation

A Reconciliation that changes allocation, beneficiary, royalty, settlement, audit, or cycle state requires authorization evidence.

---

## CVCP-67 — Supersession Integrity

A supersession must preserve Record type.

```text
Audit → Audit
Royalty → Royalty
Request → Request
Receipt → Receipt
```

---

## CVCP-68 — No Supersession Cycle

Supersession graphs must be acyclic.

---

## CVCP-69 — Single Active Record

A supersession lineage must resolve to a single current canonical Record.

---

## CVCP-70 — Reconciled Amount Conservation

Corrected downstream settlement amounts must match the corrected Royalty basis.

---

## CVCP-71 — Reversal Must Be Explicit

A reversal requires a new Receipt and external reversal evidence.

---

## CVCP-72 — Retry Preserves Identity

A simple settlement retry must not silently alter:

```text
Origin
Contribution
Audit
Royalty basis
```

---

## CVCP-73 — Reassessment Creates New Basis

If Audit is reassessed, a corrected Royalty must reference the new Audit basis.

---

## CVCP-74 — Dispute Closure Requirement

A Dispute may be marked `resolved` only when a corresponding completed Reconciliation exists.

---

## CVCP-75 — Reconciliation State Consistency

A Value Cycle may be marked `reconciled` only when a completed Reconciliation Record exists.

---

# 23. Security Boundary

CVCP must not contain raw:

* private keys;
* seed phrases;
* bank credentials;
* payment-card secrets;
* API secrets;
* authorization tokens.

Use references instead:

```text
destination_ref
authorization_ref
external_transaction_ref
external_transfer_ref
```

CVCP records evidence of authority without becoming the authority itself.

---

# 24. Validation

The reference validator is:

```text
scripts/validate_examples.py
```

It validates:

```text
Schema conformance
Causal DAG integrity
Evidence integrity
Contribution calculations
Audit confidence
Royalty calculations
Settlement integrity
Dispute integrity
Reconciliation integrity
Supersession DAG integrity
Recovery rules
Amount conservation
State continuity
Value Cycle consistency
```

Pass examples must:

```text
schema-ok
semantic-ok
```

Fail examples must intentionally produce:

```text
expected-schema-failure
```

or:

```text
expected-semantic-failure
```

The v0.5 repository is validated through GitHub Actions.

---

# 25. Conformance Principle

A CVCP implementation is not conformant merely because its JSON or YAML matches a Schema.

Conformance requires both:

```text
Structural Validity
+
Semantic Integrity
```

Therefore:

```text
JSON Schema
        ↓
Semantic Validator
        ↓
CVCP Conformance
```

---

# 26. Version Evolution

```text
v0.1 — Value Cycle
What is the value cycle?

v0.2 — Causal Integrity
Where did the value come from?

v0.3 — Contribution & Audit
How much did each Origin contribute?

v0.4 — Royalty & Settlement Interface
Was the value actually settled externally?

v0.5 — Reconciliation & Recovery
Can an incorrect completed settlement be corrected
without erasing its history?
```

---

# 27. Final Principle

CVCP v0.5 treats value not as a single payment event but as an auditable lifecycle.

```text
Origin
  ↓
Trace
  ↓
Contribution
  ↓
Audit
  ↓
Royalty
  ↓
Settlement
  ↓
Dispute
  ↓
Reconciliation
  ↓
Recovery
```

The protocol therefore preserves both:

```text
what happened
```

and:

```text
how what happened was later corrected
```

without destroying the causal record.

> **Value must be traceable when created, auditable when allocated, receipted when settled, and recoverable when wrong.**
