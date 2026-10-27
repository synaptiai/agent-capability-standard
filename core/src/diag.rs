//! Diagnostics: the error model of STANDARD §9, plus warnings.
//!
//! Every code has a fixed severity. Errors make a workflow invalid; warnings
//! never do unless the caller asks for strict mode, which promotes them.

use serde::Serialize;
use serde_json::{Map, Value};

/// Severity of a diagnostic. Fixed per [`Code`].
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize)]
#[serde(rename_all = "lowercase")]
pub enum Severity {
    Error,
    Warning,
}

macro_rules! codes {
    ($( $variant:ident = $code:literal, $name:literal, $sev:ident; )*) => {
        /// A standard error or warning code (STANDARD §9).
        #[derive(Debug, Clone, Copy, PartialEq, Eq, Hash)]
        pub enum Code { $( $variant, )* }

        impl Code {
            /// The short code string, e.g. `"V101"`.
            pub fn as_str(self) -> &'static str {
                match self { $( Code::$variant => $code, )* }
            }
            /// The canonical name, e.g. `"UNKNOWN_CAPABILITY"`.
            pub fn name(self) -> &'static str {
                match self { $( Code::$variant => $name, )* }
            }
            /// The fixed severity of this code.
            pub fn severity(self) -> Severity {
                match self { $( Code::$variant => Severity::$sev, )* }
            }
            /// Look a code up by its short string.
            pub fn from_code_str(s: &str) -> Option<Code> {
                match s { $( $code => Some(Code::$variant), )* _ => None }
            }
            /// Every code, in declaration order.
            pub const ALL: &'static [Code] = &[ $( Code::$variant, )* ];
        }
    };
}

codes! {
    UnknownCapability = "V101", "UNKNOWN_CAPABILITY", Error;
    MissingPrerequisite = "V102", "MISSING_PREREQUISITE", Error;
    InvalidStep = "V103", "INVALID_STEP", Error;
    DuplicateStoreAs = "V104", "DUPLICATE_STORE_AS", Error;
    CircularDependency = "V105", "CIRCULAR_DEPENDENCY", Error;
    UnsupportedExtension = "V106", "UNSUPPORTED_EXTENSION", Error;
    UnresolvedTarget = "V107", "UNRESOLVED_TARGET", Error;
    InvalidExpression = "V108", "INVALID_EXPRESSION", Error;
    UnsupportedSpecVersion = "V109", "UNSUPPORTED_SPEC_VERSION", Error;

    InvalidBindingPath = "B201", "INVALID_BINDING_PATH", Error;
    MissingProducer = "B202", "MISSING_PRODUCER", Error;
    TypeMismatch = "B203", "TYPE_MISMATCH", Error;
    AmbiguousType = "B204", "AMBIGUOUS_TYPE", Error;
    InvalidAnnotation = "B205", "INVALID_ANNOTATION", Error;
    ExpressionTypeError = "B206", "EXPRESSION_TYPE_ERROR", Error;

    SchemaNotFound = "S301", "SCHEMA_NOT_FOUND", Error;
    InvalidRef = "S302", "INVALID_REF", Error;
    SchemaValidationFailed = "S303", "SCHEMA_VALIDATION_FAILED", Error;
    MissingRequiredField = "S304", "MISSING_REQUIRED_FIELD", Error;

    ExecutionTimeout = "R401", "EXECUTION_TIMEOUT", Error;
    ExecutionFailed = "R402", "EXECUTION_FAILED", Error;
    GateBlocked = "R403", "GATE_BLOCKED", Error;
    RecoveryExhausted = "R404", "RECOVERY_EXHAUSTED", Error;
    ExpressionError = "R405", "EXPRESSION_ERROR", Error;
    LivenessLost = "R406", "LIVENESS_LOST", Error;

    CheckpointRequired = "F501", "CHECKPOINT_REQUIRED", Error;
    ApprovalRequired = "F502", "APPROVAL_REQUIRED", Error;
    RollbackFailed = "F503", "ROLLBACK_FAILED", Error;
    ConstraintViolated = "F504", "CONSTRAINT_VIOLATED", Error;
    ProvenanceMissing = "F505", "PROVENANCE_MISSING", Error;

    SoftRequirementUnmet = "W601", "SOFT_REQUIREMENT_UNMET", Warning;
    SafetyFlagDowngrade = "W602", "SAFETY_FLAG_DOWNGRADE", Warning;
    DeprecatedForm = "W603", "DEPRECATED_FORM", Warning;
    UnknownField = "W604", "UNKNOWN_FIELD", Warning;
    MissingSpecVersion = "W605", "MISSING_SPEC_VERSION", Warning;
    UnattendedApproval = "W606", "UNATTENDED_APPROVAL", Warning;
    UnresolvedWorkflow = "W607", "UNRESOLVED_WORKFLOW", Warning;
    WaitSpansCheckpoint = "W608", "WAIT_SPANS_CHECKPOINT", Warning;
    UntriggeredFailureMode = "W609", "UNTRIGGERED_FAILURE_MODE", Warning;
    NullableOperand = "W610", "NULLABLE_OPERAND", Warning;
    ConstantComparison = "W611", "CONSTANT_COMPARISON", Warning;
    MangledReference = "W612", "MANGLED_REFERENCE", Warning;
    UnreachableHandler = "W613", "UNREACHABLE_HANDLER", Warning;
    InvalidDuration = "W614", "INVALID_DURATION", Warning;
}

impl Serialize for Code {
    fn serialize<S: serde::Serializer>(&self, s: S) -> Result<S::Ok, S::Error> {
        s.serialize_str(self.as_str())
    }
}

/// One finding, in the §9.7 response shape plus `severity`.
///
/// `name` and `severity` are functions of `code`, so they are derived when
/// serializing rather than stored, and cannot disagree with it.
#[derive(Debug, Clone, PartialEq)]
pub struct Diagnostic {
    pub code: Code,
    pub message: String,
    pub location: Map<String, Value>,
    pub suggestion: Option<String>,
}

impl Serialize for Diagnostic {
    fn serialize<S: serde::Serializer>(&self, s: S) -> Result<S::Ok, S::Error> {
        use serde::ser::SerializeMap;
        let mut m = s.serialize_map(None)?;
        m.serialize_entry("code", self.code.as_str())?;
        m.serialize_entry("name", self.code.name())?;
        m.serialize_entry("severity", &self.code.severity())?;
        m.serialize_entry("message", &self.message)?;
        m.serialize_entry("location", &self.location)?;
        if let Some(sg) = &self.suggestion {
            m.serialize_entry("suggestion", sg)?;
        }
        m.end()
    }
}

impl Diagnostic {
    pub fn new(code: Code, message: impl Into<String>) -> Self {
        Diagnostic {
            code,
            message: message.into(),
            location: Map::new(),
            suggestion: None,
        }
    }

    /// Add a location key (`workflow`, `step`, `field`, ...).
    pub fn at(mut self, key: &str, value: impl Into<Value>) -> Self {
        self.location.insert(key.to_string(), value.into());
        self
    }

    pub fn suggest(mut self, suggestion: impl Into<String>) -> Self {
        self.suggestion = Some(suggestion.into());
        self
    }

    pub fn severity(&self) -> Severity {
        self.code.severity()
    }

    pub fn is_error(&self) -> bool {
        self.severity() == Severity::Error
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn codes_round_trip_and_are_unique() {
        let mut seen = std::collections::HashSet::new();
        for &c in Code::ALL {
            assert!(seen.insert(c.as_str()), "duplicate code {}", c.as_str());
            assert_eq!(Code::from_code_str(c.as_str()), Some(c));
        }
    }

    #[test]
    fn warnings_are_exactly_the_w_range() {
        for &c in Code::ALL {
            let is_w = c.as_str().starts_with('W');
            assert_eq!(c.severity() == Severity::Warning, is_w, "{}", c.as_str());
        }
    }

    #[test]
    fn serializes_in_standard_shape() {
        let d = Diagnostic::new(Code::UnknownCapability, "nope")
            .at("workflow", "w")
            .at("step", 3);
        let v = serde_json::to_value(&d).unwrap();
        assert_eq!(v["code"], "V101");
        assert_eq!(v["name"], "UNKNOWN_CAPABILITY");
        assert_eq!(v["severity"], "error");
        assert_eq!(v["location"]["step"], 3);
        assert!(v.get("suggestion").is_none());
    }
}
