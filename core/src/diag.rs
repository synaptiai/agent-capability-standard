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
    DuplicateBinding = "V110", "DUPLICATE_BINDING", Error;
    ToolNameMismatch = "V111", "TOOL_NAME_MISMATCH", Error;

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
    SafetyCheckFailed = "R407", "SAFETY_CHECK_FAILED", Error;
    Cancelled = "R408", "CANCELLED", Error;

    CheckpointRequired = "F501", "CHECKPOINT_REQUIRED", Error;
    ApprovalRequired = "F502", "APPROVAL_REQUIRED", Error;
    RollbackFailed = "F503", "ROLLBACK_FAILED", Error;
    ConstraintViolated = "F504", "CONSTRAINT_VIOLATED", Error;
    // A grounding policy's check of an output failed (STANDARD v1.2 §5.20).
    ProvenanceMissing = "F505", "PROVENANCE_MISSING", Error;
    GatedControlAction = "F506", "GATED_CONTROL_ACTION", Error;

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
    MissingInput = "W615", "MISSING_INPUT", Warning;
    VersionFeatureMismatch = "W616", "VERSION_FEATURE_MISMATCH", Warning;
    UnboundTool = "W617", "UNBOUND_TOOL", Warning;
    UnknownJoin = "W618", "UNKNOWN_JOIN", Warning;
    GroupMateRead = "W619", "GROUP_MATE_READ", Warning;
    NoncanonicalName = "W620", "NONCANONICAL_NAME", Warning;
    UnboundedDelegation = "W621", "UNBOUNDED_DELEGATION", Warning;
    UndeclaredDelegate = "W622", "UNDECLARED_DELEGATE", Warning;
    ConcurrentRunConflict = "W623", "CONCURRENT_RUN_CONFLICT", Warning;
    UncheckedRollback = "W624", "UNCHECKED_ROLLBACK", Warning;
    DestinationNotShown = "W625", "DESTINATION_NOT_SHOWN", Warning;
    UnknownMemoryScope = "W626", "UNKNOWN_MEMORY_SCOPE", Warning;
}

impl Serialize for Code {
    fn serialize<S: serde::Serializer>(&self, s: S) -> Result<S::Ok, S::Error> {
        s.serialize_str(self.as_str())
    }
}

/// One finding, in the §9.8 shape plus `severity`.
///
/// `name` and `severity` are functions of `code`, so they are derived when
/// serializing rather than stored, and cannot disagree with it.
#[derive(Debug, Clone, PartialEq)]
pub struct Diagnostic {
    pub code: Code,
    pub message: String,
    /// Where the finding is (STANDARD v1.2 §9.8): `workflow` (its key in
    /// the catalog), `step` (zero-based, in list order), `capability`,
    /// `field` (relative to the step, else the workflow, else the document
    /// the finding is about), `path` (an RFC 6901 pointer from the catalog
    /// root, added when a report is finished), `catalog`, and the further
    /// keys §9.8 defines.
    pub location: Map<String, Value>,
    pub suggestion: Option<String>,
    /// The JSON Pointer tokens of `location.field` (unescaped, indices as
    /// decimal strings), when the field holds a key the document chose and
    /// so cannot be split back exactly. Not serialised.
    pub(crate) segments: Option<Vec<String>>,
}

/// One segment of a `field` (§9.8): a key, or a list index.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Seg<'a> {
    Key(&'a str),
    Index(usize),
}

/// The §9.8 text of a field: keys joined by `.`, an index as `[n]` with no
/// dot before it.
pub fn field_text(segs: &[Seg<'_>]) -> String {
    let mut out = String::new();
    for seg in segs {
        match seg {
            Seg::Key(k) => {
                if !out.is_empty() {
                    out.push('.');
                }
                out.push_str(k);
            }
            Seg::Index(i) => out.push_str(&format!("[{i}]")),
        }
    }
    out
}

/// The pointer tokens of a `field` made only of names this Standard
/// defines and indices (no key contains `.`, `[` or `]`), so splitting at
/// them is exact: `gates[0].when` gives `gates`, `0`, `when`.
pub fn split_field(field: &str) -> Vec<String> {
    let mut out = Vec::new();
    for piece in field.split('.') {
        let (name, mut rest) = match piece.find('[') {
            Some(i) => (&piece[..i], &piece[i..]),
            None => (piece, ""),
        };
        if !name.is_empty() {
            out.push(name.to_string());
        }
        while let Some(stripped) = rest.strip_prefix('[') {
            let Some(end) = stripped.find(']') else {
                out.push(rest.to_string());
                break;
            };
            out.push(stripped[..end].to_string());
            rest = &stripped[end + 1..];
        }
    }
    out
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
            segments: None,
        }
    }

    /// Add a location key (`workflow`, `step`, `field`, ...). A `field`
    /// set here holds only names this Standard defines and indices; a
    /// `field` that holds a key the document chose MUST be set with
    /// [`Diagnostic::at_field`] or [`Diagnostic::at_field_key`], so that its
    /// `path` is exact (§9.8).
    pub fn at(mut self, key: &str, value: impl Into<Value>) -> Self {
        if key == "field" {
            self.segments = None;
        }
        self.location.insert(key.to_string(), value.into());
        self
    }

    /// Set `field` from segments, keeping their pointer tokens.
    pub fn at_field(mut self, segs: &[Seg<'_>]) -> Self {
        self.location
            .insert("field".to_string(), Value::String(field_text(segs)));
        self.segments = Some(
            segs.iter()
                .map(|s| match s {
                    Seg::Key(k) => (*k).to_string(),
                    Seg::Index(i) => i.to_string(),
                })
                .collect(),
        );
        self
    }

    /// Set `field` to `base` (names this Standard defines and indices)
    /// followed by `key`, a key the document chose: `input_bindings.<key>`.
    pub fn at_field_key(mut self, base: &str, key: &str) -> Self {
        let text = if base.is_empty() {
            key.to_string()
        } else {
            format!("{base}.{key}")
        };
        let mut tokens = split_field(base);
        tokens.push(key.to_string());
        self.location
            .insert("field".to_string(), Value::String(text));
        self.segments = Some(tokens);
        self
    }

    /// The pointer tokens of `field`: its segments when it was set from
    /// them, else `field` split at `.` and `[n]`.
    pub fn field_tokens(&self) -> Vec<String> {
        match (
            &self.segments,
            self.location.get("field").and_then(Value::as_str),
        ) {
            (Some(s), _) => s.clone(),
            (None, Some(f)) => split_field(f),
            (None, None) => Vec::new(),
        }
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
    fn fields_and_tokens() {
        let segs = [Seg::Key("gates"), Seg::Index(0), Seg::Key("when")];
        assert_eq!(field_text(&segs), "gates[0].when");
        assert_eq!(split_field("gates[0].when"), ["gates", "0", "when"]);
        assert_eq!(
            split_field("triggers[0].schedule.cron"),
            ["triggers", "0", "schedule", "cron"]
        );
        assert_eq!(split_field("a[1][2]"), ["a", "1", "2"]);
        let d = Diagnostic::new(Code::UnknownField, "x").at_field_key("input_bindings", "a.b");
        assert_eq!(d.location["field"], "input_bindings.a.b");
        assert_eq!(d.field_tokens(), ["input_bindings", "a.b"]);
        let d = Diagnostic::new(Code::UnknownField, "x").at_field(&segs);
        assert_eq!(d.field_tokens(), ["gates", "0", "when"]);
        // Serialisation is unchanged: segments are not written.
        let v = serde_json::to_value(&d).unwrap();
        assert_eq!(v["location"], serde_json::json!({"field": "gates[0].when"}));
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
