#!/bin/bash
# validate-schema.sh - Schema validation utility for the validate skill
# Usage: ./validate-schema.sh <schema_file> <data_file> [--format json|yaml]

set -euo pipefail

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

SCHEMA_FILE=""
DATA_FILE=""
FORMAT="auto"

usage() {
    cat << EOF
Usage: $(basename "$0") <schema_file> <data_file> [options]

Options:
  --format json|yaml    Specify data format (default: auto-detect)
  --verbose             Show detailed validation output
  --help                Show this help message

Examples:
  $(basename "$0") schema.json data.json
  $(basename "$0") schema.yaml config.yaml --format yaml
EOF
    exit 1
}

# Parse arguments
VERBOSE=false
while [[ $# -gt 0 ]]; do
    case $1 in
        --format)
            FORMAT="$2"
            shift 2
            ;;
        --verbose)
            VERBOSE=true
            shift
            ;;
        --help)
            usage
            ;;
        *)
            if [[ -z "$SCHEMA_FILE" ]]; then
                SCHEMA_FILE="$1"
            elif [[ -z "$DATA_FILE" ]]; then
                DATA_FILE="$1"
            else
                echo "Error: Unexpected argument: $1"
                usage
            fi
            shift
            ;;
    esac
done

# Validate arguments
if [[ -z "$SCHEMA_FILE" ]] || [[ -z "$DATA_FILE" ]]; then
    echo "Error: Both schema file and data file are required"
    usage
fi

if [[ ! -f "$SCHEMA_FILE" ]]; then
    echo -e "${RED}Error: Schema file not found: $SCHEMA_FILE${NC}"
    exit 1
fi

if [[ ! -f "$DATA_FILE" ]]; then
    echo -e "${RED}Error: Data file not found: $DATA_FILE${NC}"
    exit 1
fi

# Auto-detect format
detect_format() {
    local file="$1"
    local ext="${file##*.}"

    case "$ext" in
        json) echo "json" ;;
        yaml|yml) echo "yaml" ;;
        *)
            # Try to detect from content
            if head -1 "$file" | grep -q "^{"; then
                echo "json"
            elif head -1 "$file" | grep -q "^---"; then
                echo "yaml"
            else
                echo "unknown"
            fi
            ;;
    esac
}

if [[ "$FORMAT" == "auto" ]]; then
    FORMAT=$(detect_format "$DATA_FILE")
    [[ "$VERBOSE" == true ]] && echo -e "${BLUE}Auto-detected format: $FORMAT${NC}"
fi

echo "========================================"
echo "  Schema Validation"
echo "  $(date)"
echo "========================================"
echo ""
echo "Schema: $SCHEMA_FILE"
echo "Data:   $DATA_FILE"
echo "Format: $FORMAT"
echo ""

# Validation logic
validate_json() {
    local schema="$1"
    local data="$2"

    # Check if ajv (Another JSON Validator) is available
    if command -v ajv &> /dev/null; then
        echo "Using: ajv (Another JSON Validator)"
        if ajv validate -s "$schema" -d "$data" 2>&1; then
            return 0
        else
            return 1
        fi
    fi

    # Check if jsonschema (Python) is available
    if command -v jsonschema &> /dev/null; then
        echo "Using: jsonschema (Python)"
        if jsonschema -i "$data" "$schema" 2>&1; then
            return 0
        else
            return 1
        fi
    fi

    # Check if jq is available for basic validation
    if command -v jq &> /dev/null; then
        echo "Using: jq (basic JSON validation only)"
        echo -e "${YELLOW}Warning: Full schema validation not available, checking JSON syntax only${NC}"

        if jq empty "$data" 2>&1; then
            echo -e "${GREEN}JSON syntax is valid${NC}"

            # Do basic structure checks
            echo ""
            echo "Basic structure validation:"

            # Check if schema has required fields
            if jq -e '.required' "$schema" > /dev/null 2>&1; then
                REQUIRED=$(jq -r '.required[]' "$schema" 2>/dev/null)
                for field in $REQUIRED; do
                    if jq -e ".$field" "$data" > /dev/null 2>&1; then
                        echo -e "  ${GREEN}[OK]${NC} Required field present: $field"
                    else
                        echo -e "  ${RED}[MISSING]${NC} Required field: $field"
                        return 1
                    fi
                done
            fi

            return 0
        else
            return 1
        fi
    fi

    echo -e "${RED}Error: No JSON validation tool found${NC}"
    echo "Install one of: ajv-cli, jsonschema (pip), or jq"
    return 2
}

validate_yaml() {
    local schema="$1"
    local data="$2"

    # Check if yq is available
    if command -v yq &> /dev/null; then
        echo "Using: yq (YAML validation)"

        if yq eval '.' "$data" > /dev/null 2>&1; then
            echo -e "${GREEN}YAML syntax is valid${NC}"

            # Convert to JSON and validate if possible
            if command -v jq &> /dev/null; then
                echo ""
                echo "Converting to JSON for schema validation..."
                local json_data=$(mktemp)
                yq eval -o=json '.' "$data" > "$json_data"
                local json_schema=$(mktemp)
                yq eval -o=json '.' "$schema" > "$json_schema"

                validate_json "$json_schema" "$json_data"
                local result=$?

                rm -f "$json_data" "$json_schema"
                return $result
            fi

            return 0
        else
            echo -e "${RED}YAML syntax error${NC}"
            return 1
        fi
    fi

    # Fallback to Python yaml
    if command -v python3 &> /dev/null; then
        echo "Using: Python yaml module"
        python3 -c "import yaml; yaml.safe_load(open('$data'))" 2>&1
        if [[ $? -eq 0 ]]; then
            echo -e "${GREEN}YAML syntax is valid${NC}"
            return 0
        else
            return 1
        fi
    fi

    echo -e "${RED}Error: No YAML validation tool found${NC}"
    echo "Install: yq or python3 with PyYAML"
    return 2
}

# Run validation
echo "--- Validation Results ---"
echo ""

case "$FORMAT" in
    json)
        if validate_json "$SCHEMA_FILE" "$DATA_FILE"; then
            echo ""
            echo -e "${GREEN}Validation: PASSED${NC}"
            exit 0
        else
            echo ""
            echo -e "${RED}Validation: FAILED${NC}"
            exit 1
        fi
        ;;
    yaml)
        if validate_yaml "$SCHEMA_FILE" "$DATA_FILE"; then
            echo ""
            echo -e "${GREEN}Validation: PASSED${NC}"
            exit 0
        else
            echo ""
            echo -e "${RED}Validation: FAILED${NC}"
            exit 1
        fi
        ;;
    *)
        echo -e "${RED}Error: Unknown format: $FORMAT${NC}"
        echo "Please specify --format json or --format yaml"
        exit 1
        ;;
esac
