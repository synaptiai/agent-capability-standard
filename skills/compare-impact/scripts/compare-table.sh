#!/bin/bash
# compare-table.sh - Generate comparison tables for compare-* skills
# Usage: ./compare-table.sh <before_file> <after_file> [--format markdown|csv|json]

set -euo pipefail

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

BEFORE_FILE=""
AFTER_FILE=""
OUTPUT_FORMAT="markdown"
OUTPUT_FILE=""

usage() {
    cat << EOF
Usage: $(basename "$0") <before_file> <after_file> [options]

Options:
  --format markdown|csv|json  Output format (default: markdown)
  --output <file>             Write output to file instead of stdout
  --help                      Show this help message

Examples:
  $(basename "$0") state-before.json state-after.json
  $(basename "$0") v1.yaml v2.yaml --format csv
  $(basename "$0") old.json new.json --format json --output diff.json
EOF
    exit 1
}

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --format)
            OUTPUT_FORMAT="$2"
            shift 2
            ;;
        --output)
            OUTPUT_FILE="$2"
            shift 2
            ;;
        --help)
            usage
            ;;
        *)
            if [[ -z "$BEFORE_FILE" ]]; then
                BEFORE_FILE="$1"
            elif [[ -z "$AFTER_FILE" ]]; then
                AFTER_FILE="$1"
            else
                echo "Error: Unexpected argument: $1"
                usage
            fi
            shift
            ;;
    esac
done

# Validate arguments
if [[ -z "$BEFORE_FILE" ]] || [[ -z "$AFTER_FILE" ]]; then
    echo "Error: Both before and after files are required"
    usage
fi

if [[ ! -f "$BEFORE_FILE" ]]; then
    echo -e "${RED}Error: Before file not found: $BEFORE_FILE${NC}"
    exit 1
fi

if [[ ! -f "$AFTER_FILE" ]]; then
    echo -e "${RED}Error: After file not found: $AFTER_FILE${NC}"
    exit 1
fi

# Detect file type
detect_type() {
    local file="$1"
    local ext="${file##*.}"

    case "$ext" in
        json) echo "json" ;;
        yaml|yml) echo "yaml" ;;
        csv) echo "csv" ;;
        *) echo "text" ;;
    esac
}

FILE_TYPE=$(detect_type "$BEFORE_FILE")

# Compare functions
compare_json() {
    local before="$1"
    local after="$2"

    if ! command -v jq &> /dev/null; then
        echo -e "${RED}Error: jq is required for JSON comparison${NC}"
        exit 1
    fi

    # Extract keys from both files
    local before_keys=$(jq -r 'paths(scalars) | join(".")' "$before" 2>/dev/null | sort)
    local after_keys=$(jq -r 'paths(scalars) | join(".")' "$after" 2>/dev/null | sort)

    # Find added, removed, and common keys
    local all_keys=$(echo -e "$before_keys\n$after_keys" | sort -u)

    echo "{"
    echo '  "comparison": {'
    echo '    "before_file": "'"$before"'",'
    echo '    "after_file": "'"$after"'",'
    echo '    "timestamp": "'"$(date -u +%Y-%m-%dT%H:%M:%SZ)"'",'
    echo '    "changes": ['

    local first=true
    for key in $all_keys; do
        local before_val=$(jq -r ".$key // \"<absent>\"" "$before" 2>/dev/null || echo "<absent>")
        local after_val=$(jq -r ".$key // \"<absent>\"" "$after" 2>/dev/null || echo "<absent>")

        if [[ "$before_val" != "$after_val" ]]; then
            local change_type="modified"
            [[ "$before_val" == "<absent>" ]] && change_type="added"
            [[ "$after_val" == "<absent>" ]] && change_type="removed"

            [[ "$first" == "true" ]] && first=false || echo ","
            echo "      {"
            echo "        \"path\": \"$key\","
            echo "        \"type\": \"$change_type\","
            echo "        \"before\": \"$before_val\","
            echo "        \"after\": \"$after_val\""
            echo -n "      }"
        fi
    done

    echo ""
    echo "    ]"
    echo "  }"
    echo "}"
}

generate_markdown() {
    local before="$1"
    local after="$2"

    cat << EOF
# Comparison Report

**Generated:** $(date)

## Files Compared

| Property | Value |
|----------|-------|
| Before | \`$before\` |
| After | \`$after\` |

## Changes

| Path | Change Type | Before | After |
|------|-------------|--------|-------|
EOF

    if [[ "$FILE_TYPE" == "json" ]] && command -v jq &> /dev/null; then
        local before_keys=$(jq -r 'paths(scalars) | join(".")' "$before" 2>/dev/null | sort)
        local after_keys=$(jq -r 'paths(scalars) | join(".")' "$after" 2>/dev/null | sort)
        local all_keys=$(echo -e "$before_keys\n$after_keys" | sort -u)

        for key in $all_keys; do
            local before_val=$(jq -r ".$key // \"—\"" "$before" 2>/dev/null || echo "—")
            local after_val=$(jq -r ".$key // \"—\"" "$after" 2>/dev/null || echo "—")

            if [[ "$before_val" != "$after_val" ]]; then
                local change_type="Modified"
                local icon="🔄"
                [[ "$before_val" == "—" ]] && { change_type="Added"; icon="➕"; }
                [[ "$after_val" == "—" ]] && { change_type="Removed"; icon="➖"; }

                # Escape pipe characters for markdown
                before_val="${before_val//|/\\|}"
                after_val="${after_val//|/\\|}"

                echo "| \`$key\` | $icon $change_type | \`$before_val\` | \`$after_val\` |"
            fi
        done
    else
        # Fallback to diff for non-JSON files
        echo ""
        echo "### Diff Output"
        echo ""
        echo "\`\`\`diff"
        diff -u "$before" "$after" 2>/dev/null || true
        echo "\`\`\`"
    fi

    cat << EOF

## Summary

EOF

    if [[ "$FILE_TYPE" == "json" ]] && command -v jq &> /dev/null; then
        local added=$(compare_json "$before" "$after" 2>/dev/null | grep -c '"type": "added"' || echo 0)
        local removed=$(compare_json "$before" "$after" 2>/dev/null | grep -c '"type": "removed"' || echo 0)
        local modified=$(compare_json "$before" "$after" 2>/dev/null | grep -c '"type": "modified"' || echo 0)

        echo "- **Added:** $added"
        echo "- **Removed:** $removed"
        echo "- **Modified:** $modified"
    fi
}

generate_csv() {
    local before="$1"
    local after="$2"

    echo "Path,Change Type,Before,After"

    if [[ "$FILE_TYPE" == "json" ]] && command -v jq &> /dev/null; then
        local before_keys=$(jq -r 'paths(scalars) | join(".")' "$before" 2>/dev/null | sort)
        local after_keys=$(jq -r 'paths(scalars) | join(".")' "$after" 2>/dev/null | sort)
        local all_keys=$(echo -e "$before_keys\n$after_keys" | sort -u)

        for key in $all_keys; do
            local before_val=$(jq -r ".$key // \"\"" "$before" 2>/dev/null)
            local after_val=$(jq -r ".$key // \"\"" "$after" 2>/dev/null)

            if [[ "$before_val" != "$after_val" ]]; then
                local change_type="modified"
                [[ -z "$before_val" ]] && change_type="added"
                [[ -z "$after_val" ]] && change_type="removed"

                # Escape quotes for CSV
                before_val="${before_val//\"/\"\"}"
                after_val="${after_val//\"/\"\"}"

                echo "\"$key\",\"$change_type\",\"$before_val\",\"$after_val\""
            fi
        done
    fi
}

# Main output logic
output_content() {
    case "$OUTPUT_FORMAT" in
        markdown|md)
            generate_markdown "$BEFORE_FILE" "$AFTER_FILE"
            ;;
        csv)
            generate_csv "$BEFORE_FILE" "$AFTER_FILE"
            ;;
        json)
            compare_json "$BEFORE_FILE" "$AFTER_FILE"
            ;;
        *)
            echo -e "${RED}Error: Unknown format: $OUTPUT_FORMAT${NC}"
            exit 1
            ;;
    esac
}

# Output to file or stdout
if [[ -n "$OUTPUT_FILE" ]]; then
    output_content > "$OUTPUT_FILE"
    echo -e "${GREEN}Comparison saved to: $OUTPUT_FILE${NC}"
else
    output_content
fi
