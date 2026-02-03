# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/).

## [Unreleased]

### Added
- Multi-agent coordination runtime with delegate, synchronize, and invoke patterns (#98)
- NIST AI RMF 1.0 profile with tier assessments and maturity roadmap (#59)
- EU AI Act conformity assessment preparation (#58, #97)
- ISO 42001 gap analysis and certification readiness documentation (#96)
- Workflow execution engine (TD-006) (#94)
- OASF GA extension mechanism for unmapped capabilities (TD-010) (#95)
- Comprehensive analysis documentation package (13 documents, ~570KB)

### Changed
- Enhanced CLAUDE.md with workflow orchestration guidelines and core principles

### Fixed
- Install real SDK, remove all mock/skip patterns (#99)

## [v1.0.5] — 2026-01-29

### Added
- Perspective validation checklist (PVC) system (#34)
- OASF-to-Grounded-Agency capability mapping file (#32)
- OASF compatibility adapter with full test suite (#33)
- OASF-inspired workflow patterns added to catalog (#31)
- Modality handling guide for vision, audio, and multimodal domains (#30)
- Modality-specific domain profiles for vision, audio, and multi-modal (#28)
- OASF safety extensions proposal (#29)
- OASF coverage report and comparison documentation

### Fixed
- Skills made self-contained with bundled transitive dependencies (#36)

## [v1.0.4] — 2026-01-27

### Added
- Domain-specific workflow templates and default profiles (#12, #17)
- Automated validation for domain profiles (#18, #19)
- Claude Agent SDK integration with safety patterns (#11, #16)
- Benchmark suite for Grounded Agency validation (#10, #15)
- Agent failure taxonomy research (#8, #13)
- Replanning and goal uncertainty capabilities (#9, #14)
- Missing edge types to ontology (#2, #20)
- Comprehensive FAQ with rationale for rejected proposals

### Fixed
- Complete edge graph for 5 orphan capabilities (#1, #21)
- Flattened skills directory structure for Claude Code compatibility

### Changed
- Migrated capability ontology from JSON to YAML format
- Updated capability count references from 35 to 36
- Migrated from 99 to 36 atomic capabilities with domain parameterization

## [v1.0.0] — 2026-01-24

### Added
- Initial publication candidate
- Capability ontology with 36 atomic capabilities across 9 cognitive layers
- Typed I/O contracts and explicit dependencies for all capabilities
- Workflow DSL spec v2 with bindings, conditions, gates, recovery loops, parallel groups
- Canonical world state and event schemas (provenance, uncertainty, retention, lineage)
- Identity taxonomy and identity resolution policy
- Authority trust model (weights, decay, field-specific authority)
- Compiler-grade validator with $ref resolution, type inference, consumer input schema checking, and patch suggestions
- 12 reference workflows in workflow catalog
- Safety hooks (checkpoint enforcement, audit logging)
- Domain profiles for healthcare, manufacturing, data analysis, and personal assistant
- Conformance test suite with 5 fixture tests
