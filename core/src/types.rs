//! The binding type system (STANDARD §5.4): annotations, schema inference,
//! compatibility.

use std::fmt;

use serde_json::Value;

/// A binding type.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum Type {
    /// No type information; compatible with everything, but ambiguous.
    Unknown,
    /// Explicitly any value (annotation `any`).
    Any,
    Null,
    String,
    Number,
    /// A whole number; every integer is also a number.
    Integer,
    Boolean,
    Object,
    Array(Box<Type>),
    Map(Box<Type>, Box<Type>),
    Nullable(Box<Type>),
    Union(Vec<Type>),
}

impl fmt::Display for Type {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Type::Unknown => write!(f, "unknown"),
            Type::Any => write!(f, "any"),
            Type::Null => write!(f, "null"),
            Type::String => write!(f, "string"),
            Type::Number => write!(f, "number"),
            Type::Integer => write!(f, "integer"),
            Type::Boolean => write!(f, "boolean"),
            Type::Object => write!(f, "object"),
            Type::Array(t) => write!(f, "array<{t}>"),
            Type::Map(k, v) => write!(f, "map<{k},{v}>"),
            Type::Nullable(t) => write!(f, "nullable<{t}>"),
            Type::Union(opts) => {
                let s: Vec<String> = opts.iter().map(Type::to_string).collect();
                write!(f, "union<{}>", s.join(","))
            }
        }
    }
}

fn primitive(name: &str) -> Option<Type> {
    Some(match name {
        "string" => Type::String,
        "number" => Type::Number,
        "integer" => Type::Integer,
        "boolean" => Type::Boolean,
        "object" => Type::Object,
        "null" => Type::Null,
        "any" => Type::Any,
        _ => return None,
    })
}

/// Split at top-level commas (outside `<...>`).
fn split_top(s: &str) -> Vec<&str> {
    let mut out = Vec::new();
    let mut depth = 0i32;
    let mut start = 0;
    for (i, c) in s.char_indices() {
        match c {
            '<' => depth += 1,
            '>' => depth -= 1,
            ',' if depth == 0 => {
                out.push(s[start..i].trim());
                start = i + 1;
            }
            _ => {}
        }
    }
    out.push(s[start..].trim());
    out
}

/// Parse a type annotation. Unknown names are an error (B205), never a
/// silent wildcard.
pub fn parse_annotation(text: &str) -> Result<Type, String> {
    let t = text.trim();
    if let Some(p) = primitive(t) {
        return Ok(p);
    }
    let generic = |name: &str| -> Option<&str> {
        let rest = t.strip_prefix(name)?.trim_start();
        rest.strip_prefix('<')?.strip_suffix('>')
    };
    if let Some(inner) = generic("array") {
        return Ok(Type::Array(Box::new(parse_annotation(inner)?)));
    }
    if let Some(inner) = generic("nullable") {
        return Ok(Type::Nullable(Box::new(parse_annotation(inner)?)));
    }
    if let Some(inner) = generic("union") {
        let opts = split_top(inner)
            .into_iter()
            .map(parse_annotation)
            .collect::<Result<Vec<_>, _>>()?;
        if opts.len() < 2 {
            return Err(format!("union<...> needs at least two types in '{text}'"));
        }
        return Ok(Type::Union(opts));
    }
    if let Some(inner) = generic("map") {
        let parts = split_top(inner);
        if parts.len() != 2 {
            return Err(format!("map<K,V> needs two type arguments in '{text}'"));
        }
        return Ok(Type::Map(
            Box::new(parse_annotation(parts[0])?),
            Box::new(parse_annotation(parts[1])?),
        ));
    }
    Err(format!("unknown type annotation '{text}'"))
}

/// The type a schema node declares, and whether it is ambiguous (§5.4 rule 3:
/// unions, missing type metadata, unknown array item types).
pub fn schema_type(schema: &Value) -> (Type, bool) {
    let Some(obj) = schema.as_object() else {
        return (Type::Unknown, true);
    };
    for comb in ["oneOf", "anyOf", "allOf"] {
        if let Some(Value::Array(opts)) = obj.get(comb) {
            let opts = opts.iter().map(|o| schema_type(o).0).collect();
            return (Type::Union(opts), true);
        }
    }
    match obj.get("type") {
        Some(Value::Array(names)) => {
            let names: Vec<&str> = names.iter().filter_map(Value::as_str).collect();
            let non_null: Vec<&str> = names.iter().copied().filter(|n| *n != "null").collect();
            if non_null.len() == 1 && names.contains(&"null") {
                let inner = primitive(non_null[0]).unwrap_or(Type::Unknown);
                return (Type::Nullable(Box::new(inner)), false);
            }
            let opts = non_null
                .iter()
                .map(|n| primitive(n).unwrap_or(Type::Unknown))
                .collect();
            return (Type::Union(opts), true);
        }
        Some(Value::String(t)) => match t.as_str() {
            "array" => {
                let (items, amb) = schema_type(obj.get("items").unwrap_or(&Value::Null));
                let unknown_items = items == Type::Unknown;
                return (Type::Array(Box::new(items)), amb || unknown_items);
            }
            "string" | "number" | "integer" | "boolean" | "object" | "null" => {
                return (primitive(t).unwrap_or(Type::Unknown), false);
            }
            // `string|object` is the ontology's shorthand for a union.
            u if u.contains('|') => {
                let opts = u
                    .split('|')
                    .map(|n| primitive(n.trim()).unwrap_or(Type::Unknown))
                    .collect();
                return (Type::Union(opts), true);
            }
            // Includes the non-standard `any`: no usable type metadata.
            _ => {}
        },
        _ => {}
    }
    if obj.get("properties").is_some_and(Value::is_object) {
        return (Type::Object, false);
    }
    if let Some(ap @ Value::Object(_)) = obj.get("additionalProperties") {
        let (vt, amb) = schema_type(ap);
        let unknown = vt == Type::Unknown;
        return (
            Type::Map(Box::new(Type::String), Box::new(vt)),
            amb || unknown,
        );
    }
    (Type::Unknown, true)
}

/// Whether a value of type `actual` may flow where `expected` is required.
pub fn compatible(expected: &Type, actual: &Type) -> bool {
    use Type::*;
    match (expected, actual) {
        (Unknown | Any, _) | (_, Unknown | Any) => true,
        (Union(opts), _) => opts.iter().any(|o| compatible(o, actual)),
        (_, Union(opts)) => opts.iter().any(|o| compatible(expected, o)),
        (Nullable(e), Nullable(a)) => compatible(e, a),
        (Nullable(_), Null) => true,
        (Nullable(e), _) => compatible(e, actual),
        (_, Nullable(a)) => compatible(expected, a),
        (Number, Integer) => true,
        (Array(e), Array(a)) => compatible(e, a),
        (Map(ek, ev), Map(ak, av)) => compatible(ek, ak) && compatible(ev, av),
        (e, a) => std::mem::discriminant(e) == std::mem::discriminant(a),
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    fn p(s: &str) -> Type {
        parse_annotation(s).unwrap()
    }

    #[test]
    fn annotations() {
        assert_eq!(p("array<object>"), Type::Array(Box::new(Type::Object)));
        assert_eq!(
            p("map<string, array<number>>"),
            Type::Map(
                Box::new(Type::String),
                Box::new(Type::Array(Box::new(Type::Number)))
            )
        );
        assert_eq!(
            p(" nullable< integer > "),
            Type::Nullable(Box::new(Type::Integer))
        );
        assert_eq!(
            p("union<string, object>"),
            Type::Union(vec![Type::String, Type::Object])
        );
        // The printed form of an inferred type parses back to the same type.
        let inferred = schema_type(&json!({"oneOf": [{"type": "string"}, {"type": "object"}]})).0;
        assert_eq!(p(&inferred.to_string()), inferred);
        assert!(parse_annotation("union<string>").is_err());
        for bad in [
            "banana",
            "array<banana>",
            "map<string>",
            "array<object",
            "Array<object>",
        ] {
            assert!(parse_annotation(bad).is_err(), "{bad}");
        }
    }

    #[test]
    fn schema_inference() {
        assert_eq!(
            schema_type(&json!({"type": "integer"})),
            (Type::Integer, false)
        );
        assert!(schema_type(&json!({"type": "any"})).1);
        assert_eq!(
            schema_type(&json!({"type": "array", "items": {"type": "object"}})),
            (Type::Array(Box::new(Type::Object)), false)
        );
        assert!(schema_type(&json!({"type": "array"})).1);
        assert_eq!(
            schema_type(&json!({"type": ["string", "null"]})),
            (Type::Nullable(Box::new(Type::String)), false)
        );
        assert!(schema_type(&json!({"type": "string|object"})).1);
        assert_eq!(
            schema_type(&json!({"properties": {}})),
            (Type::Object, false)
        );
        assert!(schema_type(&json!({})).1);
    }

    #[test]
    fn compatibility() {
        assert!(compatible(&Type::Number, &Type::Integer));
        assert!(!compatible(&Type::Integer, &Type::Number));
        assert!(!compatible(&Type::String, &Type::Number));
        assert!(compatible(
            &p("array<object>"),
            &Type::Array(Box::new(Type::Unknown))
        ));
        assert!(!compatible(&p("array<string>"), &p("array<object>")));
        assert!(compatible(&p("nullable<string>"), &Type::Null));
        assert!(compatible(&Type::String, &p("nullable<string>")));
        assert!(compatible(&Type::Any, &Type::Object));
        assert!(compatible(
            &Type::Union(vec![Type::String, Type::Object]),
            &Type::Object
        ));
    }
}
