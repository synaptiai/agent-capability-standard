# Notified Body Assessment — EU AI Act Articles 43, 39

**Regulation:** EU AI Act (Regulation 2024/1689)
**Articles:** 43 (Conformity Assessment), 39 (Notified Bodies)
**Framework:** Grounded Agency (Agent Capability Standard v2.0.0)
**Status:** Reference analysis — Decision tree for conformity assessment route selection

---

## 1. Purpose

This document provides a decision framework for determining whether an AI system built on the Grounded Agency framework requires involvement of a notified body (third-party conformity assessment) or may use internal conformity assessment. It implements the conformity assessment routing defined in Art. 43 and references the notified body requirements of Art. 39.

## 2. Conformity Assessment Routes

The EU AI Act defines two primary conformity assessment procedures for high-risk AI systems:

| Route | Procedure | Basis | When Required |
|-------|-----------|-------|---------------|
| **Internal Control** | Annex VI | Art. 43(1) | Default for most high-risk AI systems not covered by specific Union harmonisation legislation |
| **Notified Body** | Annex VII | Art. 43(1), second subparagraph | Required for AI systems referred to in Annex III, point 1 (biometric categorisation and identification) unless listed exceptions apply |

### 2.1 Annex VI — Internal Control Procedure

Under the internal control procedure, the provider:

1. Verifies the quality management system complies with Art. 17 (see EUAIA-QMS-001)
2. Examines information in the technical documentation (see EUAIA-TEC-001) to assess compliance with Art. 8-15
3. Verifies the design and development process and post-market monitoring (see EUAIA-PMM-001)
4. Issues an EU declaration of conformity (Art. 47)
5. Affixes the CE marking (Art. 48)

**No external involvement required.** The provider self-certifies.

### 2.2 Annex VII — Conformity Assessment with Notified Body

Under the notified body procedure:

1. The provider selects a notified body designated under Art. 39
2. The notified body assesses the quality management system (Art. 17)
3. The notified body assesses the technical documentation
4. The notified body issues a certificate
5. The provider issues an EU declaration of conformity referencing the certificate
6. The provider affixes the CE marking

**External involvement required.** A designated third party verifies compliance.

## 3. Decision Tree

### 3.1 Primary Decision Flow

```
Is the AI system classified as high-risk?
├── NO → No conformity assessment required under Art. 43
│        (Limited risk: Art. 50 transparency only)
│        (Minimal risk: Voluntary codes of practice only)
│
└── YES → Is the system listed under Annex III, point 1?
          (Biometric categorisation or identification)
          │
          ├── YES → Has the provider applied harmonised standards
          │         (Art. 40) or common specifications (Art. 41)
          │         covering the requirements of Art. 9-15?
          │         │
          │         ├── YES → Provider may choose:
          │         │         (a) Internal control (Annex VI), OR
          │         │         (b) Notified body (Annex VII)
          │         │
          │         └── NO → NOTIFIED BODY REQUIRED (Annex VII)
          │
          └── NO → Is the system covered by Union harmonisation
                   legislation listed in Annex I, Section A?
                   │
                   ├── YES → Follow the conformity assessment
                   │         procedure of that legislation
                   │         (Art. 43(3))
                   │
                   └── NO → INTERNAL CONTROL (Annex VI)
```

### 3.2 Decision Criteria for Annex III, Point 1

Annex III, point 1 covers:

| Sub-point | Description | Trigger |
|-----------|-------------|---------|
| 1(a) | AI systems intended for **biometric identification** of natural persons | Face recognition, fingerprint matching, iris scanning |
| 1(b) | AI systems intended for **biometric categorisation** according to sensitive attributes | Categorising by race, political opinion, trade union membership, religion, sex life/orientation |
| 1(c) | AI systems intended for **emotion recognition** | Inferring emotions from facial expressions, voice, body language |

**Note:** Real-time remote biometric identification in publicly accessible spaces is *prohibited* under Art. 5(1)(h), with narrow law enforcement exceptions. Such systems are not merely high-risk — they are banned.

## 4. Domain Profile Assessment Matrix

### 4.1 Assessment per Profile

| Domain Profile | Annex III Point 1 Applicable? | Recommended Route | Rationale |
|---------------|:---:|---|---|
| **Healthcare** | No (unless biometric-based diagnostics) | Internal Control (Annex VI) | Clinical decision support is Area 5(a), not Area 1. Medical device regulation (2017/745) may impose additional conformity requirements via Art. 43(3) |
| **Manufacturing** | No | Internal Control (Annex VI) | Safety component classification under Area 2(b). Machinery Regulation (2023/1230) conformity may apply via Art. 43(3) |
| **Personal Assistant** | No | Not required (Limited Risk) | Art. 50 transparency obligations only |
| **Data Analysis** | No (unless biometric processing) | Internal Control (Annex VI) if high-risk | Only high-risk if deployed in Annex III Areas 4-5 contexts |
| **Vision** | **Potentially yes** | Conservative: Notified Body (Annex VII) | If the vision system can perform facial recognition or biometric categorisation, Annex III point 1 applies |
| **Audio** | **Potentially yes** | Conservative: Notified Body (Annex VII) | If the audio system can perform speaker identification or emotion recognition, Annex III point 1 applies |
| **Multimodal** | **Potentially yes** | Conservative: Notified Body (Annex VII) | Inherits from component modalities; if any component triggers point 1, the system triggers point 1 |

### 4.2 Biometric Capability Assessment

The following capabilities, when combined with certain domain parameters, may implicate Annex III point 1:

| Capability | Domain Parameter | Biometric Implication | Profile(s) Affected |
|-----------|-----------------|----------------------|---------------------|
| `detect` | `domain: image.face` | Facial detection is a precursor to identification | vision, multimodal |
| `classify` | `domain: image.person` | Person classification may involve biometric categorisation | vision, multimodal |
| `detect` | `domain: audio.speaker` | Speaker detection enables identification | audio, multimodal |
| `classify` | `domain: audio.emotion` | Emotion recognition from voice | audio, multimodal |
| `compare` | `domain: image.biometric` | Biometric matching/verification | vision, multimodal |
| `compare` | `domain: audio.voiceprint` | Voiceprint comparison | audio, multimodal |

**Recommendation:** If any deployed AI system uses the capability+domain combinations above, the system should be assessed under Annex III point 1, and the provider should either:
1. Apply harmonised standards fully (enabling the choice between Annex VI and VII), or
2. Engage a notified body (Annex VII)

## 5. Harmonised Standards and Common Specifications

### 5.1 Current Status

As of the framework's current version, the following standards landscape applies:

| Standard/Specification | Status | Relevance |
|----------------------|--------|-----------|
| ISO/IEC 42001:2023 (AIMS) | Published | Quality management system (Art. 17); see ISO 42001 compliance suite |
| ISO/IEC 23894:2023 (AI risk management) | Published | Risk management (Art. 9) |
| ISO/IEC 25059 (AI system quality) | Published | Accuracy, robustness (Art. 15) |
| EU harmonised standards for AI Act | In development (CEN/CENELEC JTC 21) | Not yet available for presumption of conformity |
| Common specifications (Art. 41) | Not yet adopted | European Commission implementing acts pending |

**Implication:** Until harmonised standards are adopted, providers of Annex III point 1 systems cannot rely on harmonised standards to use the internal control route. Therefore, **notified body engagement is recommended for vision, audio, and multimodal profiles** with biometric capability until harmonised standards become available.

### 5.2 Framework Alignment with Emerging Standards

The Grounded Agency framework's structural properties align with anticipated standard requirements:

| Anticipated Requirement | Framework Implementation | Alignment |
|------------------------|--------------------------|-----------|
| Risk management process | Three-tier model in ontology | Strong — structural enforcement, not just process |
| Data governance | EvidenceStore with provenance | Strong — typed evidence anchors |
| Documentation | Formal specification (whitepaper), ontology, methodology docs | Strong — exceeds typical documentation |
| Logging | Audit hook, append-only log | Strong — automatic, non-bypassable |
| Human oversight | Domain profiles with `block_autonomous`, approval gates | Strong — configurable per domain |
| Accuracy and robustness | Confidence thresholds, trust decay, 6 validators | Moderate — validators check structure, not ML performance |

## 6. Notified Body Selection Criteria

When notified body engagement is required or recommended, the provider should select a body that:

| Criterion | Requirement | Reference |
|-----------|-------------|-----------|
| Designation | Designated by an EU Member State's notifying authority | Art. 39, 28 |
| Competence | Technical competence in the relevant Annex III area | Art. 39(5) |
| Independence | No conflict of interest with the provider | Art. 39(3) |
| AI-specific expertise | Knowledge of AI-specific risks, data governance, ML lifecycle | Art. 39(5)(d) |
| Accreditation | Accredited by a national accreditation body per Regulation (EC) 765/2008 | Art. 39(1) |

**NANDO database:** The EU's NANDO database (New Approach Notified and Designated Organisations) will list designated notified bodies once the notification process is complete.

## 7. Conformity Assessment Timeline

| Milestone | Description | Estimated Duration |
|-----------|-------------|-------------------|
| Risk classification (EUAIA-CLS-001) | Determine risk tier and applicable Annex III area | Pre-assessment |
| Route determination (this document) | Select internal control or notified body route | Pre-assessment |
| Technical documentation preparation (EUAIA-TEC-001) | Compile all required documentation | Provider effort varies |
| QMS assessment (EUAIA-QMS-001) | Internal or external QMS audit | 2-4 weeks (internal); 4-8 weeks (notified body) |
| Technical documentation review | Internal or external documentation assessment | 2-4 weeks (internal); 8-12 weeks (notified body) |
| Certificate issuance (if notified body) | Notified body issues conformity certificate | Upon successful assessment |
| Declaration of conformity (Art. 47) | Provider issues EU declaration of conformity | Upon completion |
| CE marking (Art. 48) | Provider affixes CE marking | Upon declaration |
| Post-market monitoring (EUAIA-PMM-001) | Ongoing monitoring commences | Continuous |

---

## Document Control

| Field | Value |
|-------|-------|
| Document ID | EUAIA-NTB-001 |
| Version | 1.0 |
| Effective Date | [YYYY-MM-DD] |
| Next Review Date | [YYYY-MM-DD] |
| Approved By | [Name, Title] |
| Assessment Owner | [Name, Title] |

---

*This document provides a decision framework for conformity assessment routing under EU AI Act Art. 43. The conservative recommendation for vision, audio, and multimodal profiles reflects the current absence of harmonised standards for Annex III point 1 systems. When harmonised standards become available (CEN/CENELEC JTC 21), the internal control route may become available for these profiles. All bracketed fields should be adapted to organizational context. For risk classification, see EUAIA-CLS-001. For QMS requirements, see EUAIA-QMS-001. For technical documentation, see EUAIA-TEC-001.*
