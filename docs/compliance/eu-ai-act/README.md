# EU AI Act Conformity Assessment Preparation

**Regulation:** EU AI Act (Regulation 2024/1689)
**Framework:** Grounded Agency (Agent Capability Standard v2.0.0)
**Suite Status:** Reference implementation — Adapt bracketed fields to organizational context

---

## Overview

This document suite prepares for EU AI Act conformity assessment by mapping the Grounded Agency framework's 36 capabilities, 7 domain profiles, and safety model to the regulation's requirements for high-risk AI systems.

**Key principle:** The Grounded Agency framework is *infrastructure*, not an AI system. Risk classification depends on the deployment context, not the framework alone. These documents demonstrate the framework's structural readiness for each risk tier.

## Document Register

| Doc ID | Document | Article | Purpose | Lines |
|--------|----------|---------|---------|-------|
| EUAIA-CLS-001 | [Risk Classification](risk_classification.md) | Art. 6 | Maps 7 domain profiles to EU AI Act risk categories | ~250 |
| EUAIA-PMM-001 | [Post-Market Monitoring](post_market_monitoring.md) | Art. 61 | Data collection, KPIs, escalation, incident reporting | ~300 |
| EUAIA-NTB-001 | [Notified Body Assessment](notified_body_assessment.md) | Art. 43, 39 | Decision tree for conformity assessment route selection | ~180 |
| EUAIA-QMS-001 | [Quality Management System](quality_management_system.md) | Art. 17 | Maps Art. 17(a)-(k) to framework implementations | ~350 |
| EUAIA-TEC-001 | [Annex IV Technical Documentation](annex_iv_technical_documentation.md) | Art. 11 | Covers all 7 Annex IV required elements | ~550 |

## Relationship to ISO 42001 Suite

This EU AI Act suite complements the [ISO 42001 compliance suite](../iso42001/) by mapping the same framework to EU regulatory requirements. The two suites share a common foundation:

| ISO 42001 Document | EU AI Act Cross-Reference | Overlap |
|--------------------|--------------------------|---------|
| AIMS-RSK-001 (Risk Treatment Plan) | EUAIA-CLS-001, EUAIA-QMS-001 §3.5 | Risk classification and treatment |
| AIMS-NCR-001 (Nonconformity Procedure) | EUAIA-PMM-001 §7, EUAIA-QMS-001 §3.7 | Incident handling and corrective action |
| AIMS-MGR-001 (Management Review) | EUAIA-PMM-001 §8, EUAIA-QMS-001 §3.11 | Review cadence and accountability |
| AIMS-AUD-001 (Internal Audit Checklist) | EUAIA-QMS-001 §3.11 | Audit objectives and programme |
| AIMS-CMP-001 (Competency Framework) | EUAIA-QMS-001 §3.10, §3.11 | Roles and competencies |
| AIMS-STK-001 (Stakeholder Analysis) | EUAIA-QMS-001 §3.8 | Stakeholder communication |
| AIMS-POL-001 (AI Policy Template) | EUAIA-QMS-001 §5 | Policy documentation |

## Reading Order

For initial assessment:
1. **EUAIA-CLS-001** — Understand your risk classification first
2. **EUAIA-NTB-001** — Determine your conformity assessment route
3. **EUAIA-QMS-001** — Map your QMS to Art. 17 requirements
4. **EUAIA-PMM-001** — Establish your post-market monitoring plan
5. **EUAIA-TEC-001** — Compile your technical documentation package

For regulatory submission:
1. **EUAIA-TEC-001** — Primary submission document (Annex IV)
2. **EUAIA-QMS-001** — Supporting QMS evidence (Art. 17)
3. **EUAIA-PMM-001** — Post-market monitoring plan (Art. 61)
4. **EUAIA-CLS-001** — Risk classification justification (Art. 6)
5. **EUAIA-NTB-001** — Assessment route determination (Art. 43)

## Usage Instructions

### For Framework Deployers

1. Start with **EUAIA-CLS-001** to determine your deployment's risk classification
2. If classified as high-risk, follow **EUAIA-NTB-001** to determine your conformity assessment route
3. Complete all bracketed `[YYYY-MM-DD]` and `[Name, Title]` fields with your organizational details
4. Use **EUAIA-QMS-001** as a checklist to verify your QMS coverage
5. Use **EUAIA-TEC-001** as the basis for your Annex IV submission

### For Auditors and Assessors

1. Start with **EUAIA-TEC-001** for the comprehensive technical overview
2. Cross-reference **EUAIA-CLS-001** for risk classification justification
3. Verify **EUAIA-QMS-001** Art. 17 compliance matrix
4. Review **EUAIA-PMM-001** for monitoring plan adequacy
5. Confirm assessment route per **EUAIA-NTB-001**

## Version History

| Version | Date | Changes |
|---------|------|---------|
| 1.0 | [YYYY-MM-DD] | Initial release — 5 documents covering Art. 6, 11, 17, 43, 61 |

---

*This suite is maintained alongside the framework. When the capability ontology, domain profiles, or safety model changes, these documents should be reviewed and updated per EUAIA-PMM-001 plan review triggers.*
