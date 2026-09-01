# Civilization Value Cycle Protocol

**CVCP — Civilization Value Cycle Protocol**

A protocol specification for tracing value from **Origin → Derivative → Trace → Contribution → Audit → Royalty → Settlement → Reconciliation** in AI-driven and agentic systems.

Current version:

```text
v0.5.0 — Reconciliation & Recovery
```

---

## Why CVCP?

AI systems increasingly:

* consume external knowledge;
* combine multiple sources;
* make decisions;
* generate commercially valuable outputs;
* invoke paid tools and APIs;
* perform transactions;
* act through autonomous agents.

But a fundamental question remains:

> **Where did the value come from, who contributed to it, how was that contribution evaluated, was value actually returned, and what happens if the result was wrong?**

CVCP provides a machine-readable structure for answering that question.

---

# Core Value Cycle

```text
Origin
  ↓
Derivative
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
  ↓
External Settlement
  ↓
Settlement Receipt
  ↓
Dispute
  ↓
Reconciliation
  ↓
Recovery
```

CVCP is not a payment network.

It is the **trace, attribution, audit, and value-lifecycle layer around payment**.

---

# v0.5 — Reconciliation & Recovery

v0.5 introduces a critical rule:

> **A completed settlement must remain correctable without erasing its history.**

Real systems fail.

A settlement may contain:

* a wrong beneficiary;
* an incorrect amount;
* duplicated execution;
* missing execution;
* incorrect contribution assessment;
* disputed attribution;
* incorrect Audit;
* invalid authorization.

A trustworthy Value Cycle therefore cannot end at:

```text
settled
```

It must also support:

```text
settled
  ↓
disputed
  ↓
reconciliation
  ↓
correction
  ↓
recovery
```

---

# Key Principle: Append-Only Correction

CVCP does not silently overwrite historical records.

Wrong:

```text
Royalty r001 = 10
      ↓
edit
      ↓
Royalty r001 = 9
```

Correct:

```text
Royalty r001 = 10
      ↓
Reconciliation
      ↓
Royalty r002 = 9
```

The original record remains part of the audit history.

```text
Correction
must create history,
not destroy history.
```

---

# Fourteen Schemas

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

# Architectural Layers

## 1. Origin Layer

Defines the root asset.

```text
OID
```

The Origin contains rights, licensing, attribution, royalty, provenance, and policy information.

---

## 2. Derivative Layer

Declares that an output depends on one or more Origins.

```text
Origin
  ↓
Derivative
```

---

## 3. Trace Layer

Records what actually happened.

```text
reference
transform
reasoning
decision
action
result
```

Trace is evidence.

It is not automatically judgment.

---

## 4. Evidence Layer

Evaluates the quality and relevance of Trace evidence.

```text
Trace
  ↓
Evidence Assessment
```

---

## 5. Contribution Layer

Estimates how much each Origin contributed.

```text
Evidence
  ↓
Contribution
```

Contribution must be explainable rather than arbitrarily assigned.

---

## 6. Audit Layer

Evaluates Evidence and Contribution.

```text
Contribution
  ↓
Audit
```

Audit includes explicit confidence and status.

---

## 7. Royalty Layer

Converts audited contribution into value allocation.

```text
Audit
  ↓
Royalty
```

Important:

```text
Royalty ≠ Payment
```

A Royalty describes what should be returned.

---

## 8. Settlement Layer

Settlement is executed externally.

```text
Royalty
  ↓
Settlement Request
  ║
  ║ Settlement Boundary
  ║
External Executor
  ↓
Settlement Receipt
```

CVCP never requires possession of payment credentials or private keys.

---

## 9. Dispute Layer

v0.5 introduces explicit disputes.

```text
Settlement
  ↓
Dispute
```

A Dispute must identify exactly what is challenged.

---

## 10. Reconciliation Layer

A Reconciliation records:

```text
cause
affected records
resolution actions
resulting records
authorization
outcome
```

This allows correction without destroying history.

---

# Supersession

Corrected records may contain:

```text
supersedes_ref
```

Supported families include:

```text
Audit → Audit
Royalty → Royalty
Settlement Request → Settlement Request
Settlement Receipt → Settlement Receipt
```

The supersession graph must remain acyclic.

---

# Recovery Depth

CVCP does not require every problem to restart from Origin.

## Settlement Recovery

```text
Settlement failed
      ↓
Retry
```

Origin, Trace, Audit, and Royalty remain unchanged.

## Royalty Recovery

```text
Royalty incorrect
      ↓
Reconciliation
      ↓
New Royalty
```

## Audit Recovery

```text
Contribution disputed
      ↓
Reconciliation
      ↓
Audit reassessment
```

## Causal Recovery

If Origin or Trace integrity is invalid, recovery may return to the causal layer.

This makes recovery proportional to the actual failure.

---

# State Model

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

Canonical path:

```text
Origin
  ↓
Derivative
  ↓
Trace
  ↓
Audit
  ↓
Royalty
  ↓
Settlement
  ↓
Settled
```

Reconciliation path:

```text
Settled
  ↓
Disputed
  ↓
Reconciliation Pending
  ↓
Reconciliation Processing
  ↓
Reconciled
```

---

# Validation

Run:

```bash
python scripts/validate_examples.py
```

The validator checks both JSON Schema conformance and semantic integrity.

It covers:

* Origin references;
* causal parent integrity;
* Trace DAG cycles;
* Trace Chain completeness;
* Evidence membership;
* Contribution calculations;
* normalization;
* Audit confidence;
* Royalty calculations;
* Settlement Request authorization;
* Settlement amount preservation;
* Settlement Receipt integrity;
* idempotency;
* Dispute subject resolution;
* Reconciliation references;
* resolution-action compatibility;
* supersession self-reference;
* supersession cycles;
* settlement retry invariants;
* corrected amount conservation;
* state continuity;
* final Value Cycle consistency.

The repository also runs validation through GitHub Actions.

---

# Example Philosophy

`examples/pass/`

contains valid protocol histories.

`examples/fail/`

contains deliberately invalid records and semantic scenarios.

A valid implementation must distinguish:

```text
structurally invalid
```

from:

```text
structurally valid
but semantically invalid
```

Therefore CVCP conformance is:

```text
JSON Schema
+
Semantic Validation
```

---

# Security Boundary

Do not place raw secrets inside CVCP records.

Do not store:

```text
private key
seed phrase
bank password
card secret
API secret
authorization token
```

Use references instead:

```text
destination_ref
authorization_ref
external_transfer_ref
external_transaction_ref
```

CVCP records authority evidence.

It does not become the authority.

---

# Version History

```text
v0.1
Value Cycle

v0.2
Causal Integrity

v0.3
Contribution & Audit Model

v0.4
Royalty & Settlement Interface

v0.5
Reconciliation & Recovery
```

The evolution can be summarized as:

```text
Where did value come from?
        ↓
How was it transformed?
        ↓
Who contributed?
        ↓
How was that judged?
        ↓
How much value should return?
        ↓
Was settlement actually executed?
        ↓
Can a wrong settlement be corrected
without deleting history?
```

---

# Design Position

CVCP treats value attribution as infrastructure rather than as a one-time payment calculation.

The protocol is designed around:

```text
Origin
Trace
Attribution
Audit
Settlement
Correction
```

rather than around a single centralized authority.

The long-term objective is interoperability between systems that need to exchange verifiable value provenance and settlement evidence.

---

# Current Status

**v0.5.0 — Reconciliation & Recovery**

The current v0.5 schema and example suite validates successfully through the repository validation workflow.

The protocol now covers the full path from Origin through external settlement and post-settlement correction.

---

## Core Statement

> **Value must be traceable when created, auditable when allocated, receipted when settled, and recoverable when wrong.**
