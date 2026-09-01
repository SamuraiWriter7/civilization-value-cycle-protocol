# Changelog

All notable changes to the Civilization Value Cycle Protocol (CVCP) are documented in this file.

The project follows an incremental protocol-development model in which each release extends the previous value lifecycle without removing its causal history.

---

# [0.5.0] — Reconciliation & Recovery

## Added

### Dispute Record

Added:

```text
schemas/dispute-record.schema.json
```

The new `DisputeRecord` makes disputes explicit protocol events rather than representing them only through a `disputed` state.

A dispute now records:

* Value Cycle;
* disputed subject type;
* disputed subject reference;
* dispute type;
* actor;
* evidence;
* requested resolution;
* dispute status;
* optional Reconciliation reference.

Added identifier:

```text
DPID:<actor>/<timestamp>/<nonce>
```

Supported dispute subjects include:

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

---

### Reconciliation Record

Added:

```text
schemas/reconciliation-record.schema.json
```

The new `ReconciliationRecord` records how disputes, settlement failures, incorrect allocations, or other inconsistencies are resolved.

Added identifier:

```text
RCID:<resolver>/<timestamp>/<nonce>
```

Reconciliation now explicitly records:

```text
cause
affected records
resolution type
resolution actions
resulting records
authorization
status
```

Supported resolution types include:

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

Supported action types include:

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

---

### Append-Only Correction Model

Introduced the v0.5 principle:

> **A completed settlement must remain correctable without erasing its history.**

Historical Records must not be silently replaced.

Correction is represented through new Records and explicit causal links.

---

### Supersession

Added `supersedes_ref` support to:

```text
Audit Record
Royalty Record
Settlement Request Record
Settlement Receipt Record
```

Supersession allows:

```text
old record
   ↓
new corrected record
```

while preserving the old Record for auditability.

---

### Settlement Reversal

Added:

```text
execution_status: reversed
```

to Settlement Receipt handling.

A reversal is represented through a new Receipt rather than by modifying the original settlement.

Reversal Receipts require explicit external evidence and supersession.

---

### Recovery Depth

Introduced recovery at multiple depths.

```text
Level 1
Settlement Recovery

Level 2
Royalty Recovery

Level 3
Audit Recovery

Level 4
Causal Recovery
```

This allows recovery to return only to the minimum necessary protocol layer.

---

### Reconciliation States

Added:

```text
reconciliation_pending
reconciliation_processing
reconciled
```

to the Value Cycle state model.

Canonical dispute/reconciliation flow:

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

---

### New v0.5 Invariants

Added:

```text
CVCP-59  Explicit Dispute Subject
CVCP-60  Dispute Evidence Requirement
CVCP-61  Existing Subject Requirement
CVCP-62  No Silent Mutation
CVCP-63  Reconciliation Requires Cause
CVCP-64  Resolution Traceability
CVCP-65  Result Traceability
CVCP-66  Authorization Required for Value Mutation
CVCP-67  Supersession Integrity
CVCP-68  No Supersession Cycle
CVCP-69  Single Active Record
CVCP-70  Reconciled Amount Conservation
CVCP-71  Reversal Must Be Explicit
CVCP-72  Retry Preserves Identity
CVCP-73  Reassessment Creates New Basis
CVCP-74  Dispute Closure Requirement
CVCP-75  Reconciliation State Consistency
```

All v0.1–v0.4 invariants remain conceptually preserved.

---

## Changed

### Protocol Version

Updated schemas and examples to:

```yaml
protocol_version: "0.5"
```

---

### Schema Count

Expanded the protocol from twelve to fourteen schemas.

```text
12
↓
14
```

New schemas:

```text
dispute-record.schema.json
reconciliation-record.schema.json
```

---

### Audit Record

Added optional:

```text
supersedes_ref
```

to support append-only Audit reassessment.

---

### Royalty Record

Added optional:

```text
supersedes_ref
```

to support Royalty recalculation without overwriting previous allocations.

---

### Settlement Request Record

Added optional:

```text
supersedes_ref
```

to support retry and corrected reissue.

---

### Settlement Receipt Record

Extended Settlement Receipt semantics to support:

```text
processing
settled
failed
disputed
reversed
```

and append-only supersession.

---

### Value Cycle Record

Added:

```text
dispute_refs
reconciliation_refs
```

The Value Cycle can now represent post-settlement correction history.

---

### State Transition Record

Extended the state model with reconciliation states.

---

### Validator

Updated:

```text
scripts/validate_examples.py
```

for v0.5.

New semantic validation includes:

* Dispute subject resolution;
* Dispute subject-type consistency;
* Value Cycle membership;
* resolved-Dispute Reconciliation requirement;
* Reconciliation cause validation;
* affected-record resolution;
* resulting-record resolution;
* resolution-action compatibility;
* authorization requirements;
* supersession self-reference detection;
* supersession chronological integrity;
* supersession cycle detection;
* settlement retry identity checks;
* reversal integrity;
* Audit reassessment basis checks;
* corrected Royalty / Settlement amount conservation;
* reconciliation state integrity.

---

### Historical State Validation

Changed historical Settlement transition validation so that a final Value Cycle may reference a newer Settlement Request while earlier State Transitions continue to cite the Request that actually existed at that historical point.

This prevents final snapshots from invalidating append-only historical evidence.

---

## Validation

v0.5 passes the repository GitHub Actions validation workflow.

The validated architecture now covers:

```text
Origin
→ Derivative
→ Trace
→ Evidence
→ Contribution
→ Audit
→ Royalty
→ Settlement
→ Dispute
→ Reconciliation
→ Recovery
```

---

# [0.4.0] — Royalty & Settlement Interface

## Added

Added explicit separation between calculated Royalty and externally executed settlement.

Introduced:

```text
settlement-request-record.schema.json
settlement-receipt-record.schema.json
```

Architecture:

```text
Royalty
  ↓
Settlement Request
  ║
External Settlement Executor
  ║
Settlement Receipt
```

Established:

> **CVCP calculates value. External systems execute settlement.**

---

### Settlement Boundary

Defined CVCP as the settlement metadata plane rather than the money-execution plane.

Introduced external execution references instead of requiring private payment credentials.

---

### Idempotency

Added Settlement Request idempotency keys to reduce duplicate execution risk.

---

### Settlement States

Added:

```text
settlement_pending
settlement_processing
settlement_failed
settled
```

---

### v0.4 Invariants

Added settlement integrity constraints covering:

* verified Royalty basis;
* authorization;
* unit preservation;
* amount preservation;
* idempotency;
* Request/Receipt consistency;
* missing allocations;
* extra allocations;
* external transaction evidence;
* Settlement failure;
* retry;
* Receipt immutability.

---

# [0.3.0] — Contribution & Audit Model

## Added

Introduced explicit separation:

```text
Evidence
  ↓
Contribution
  ↓
Confidence
```

Added:

```text
evidence-assessment-record.schema.json
contribution-assessment-record.schema.json
```

---

### Contribution Methodology

Added explainable weighted contribution methodology.

Baseline:

```text
reference_depth                0.15
transformation_dependency      0.25
reasoning_influence            0.20
decision_influence             0.20
outcome_influence              0.20
```

Added evidence adjustment and normalized contribution weights.

Established:

> **Contribution must be explainable, not merely assigned.**

---

### Audit Confidence

Added confidence components:

```text
evidence_quality
trace_completeness
contribution_stability
methodology_reliability
conflict_penalty
```

Added Audit statuses:

```text
verified
provisional
disputed
rejected
```

---

# [0.2.0] — Causal Integrity

## Added

Expanded the initial Value Cycle with explicit causal Trace structure.

Architecture:

```text
Origin
  ↓
Derivative
  ↓
Trace Event
  ↓
Trace Chain
  ↓
Audit
  ↓
Royalty
  ↓
State Transition
  ↓
Value Cycle
```

Established:

> **A value return is trustworthy only when its causal path is reconstructable.**

---

### Trace DAG

Added:

```text
previous_trace_id
causal_parent_refs
```

and semantic validation for:

* parent existence;
* scope;
* precedence;
* temporal consistency;
* causal cycles;
* chain completeness;
* terminal integrity.

---

### State Transition

Added auditable Value Cycle state transitions and continuity validation.

---

# [0.1.0] — Value Cycle Foundation

## Added

Established the initial Civilization Value Cycle Protocol model.

Core architecture:

```text
Origin
  ↓
Derivative
  ↓
Audit
  ↓
Royalty
```

The initial release defined the basic premise that value attribution should form a reconstructable lifecycle rather than a disconnected payment event.

It established the conceptual foundation for later:

```text
Trace
Contribution
Settlement
Reconciliation
```

layers.

---

# Version Trajectory

```text
v0.1
Value Cycle
"What is the value cycle?"

v0.2
Causal Integrity
"Where did the value come from?"

v0.3
Contribution & Audit
"How much did each Origin contribute?"

v0.4
Royalty & Settlement Interface
"Was the value actually settled?"

v0.5
Reconciliation & Recovery
"Can an incorrect settlement be corrected
without erasing its history?"
```

---

# Current

```text
Civilization Value Cycle Protocol
v0.5.0
Reconciliation & Recovery
```

Core principle:

> **Value must be traceable when created, auditable when allocated, receipted when settled, and recoverable when wrong.**
