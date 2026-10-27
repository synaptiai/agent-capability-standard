// Command cel_differential checks that ACS condition expressions stay a
// compatible profile of CEL (STANDARD v1.1 §5.8).
//
// For every case in tests/conformance/expressions/eval.json that ACS accepts,
// it hoists each ${...} reference into an opaque CEL variable bound to the
// value ACS resolves it to, parses the result with cel-go, and evaluates it.
// The contract is one-way: every expression ACS accepts must also be valid
// CEL, and wherever CEL returns a value, it must equal the ACS result. ACS may
// report an error (R405) where CEL returns a value only for the documented
// divergences listed in allowedDivergences. JSON numbers are bound as CEL
// doubles, CEL's own JSON mapping and the ACS number model.
//
// Every expression check.json accepts (no V108 or B205 expected) must also
// parse as CEL once hoisted.
//
// Usage (from this directory, which holds the Go module):
//
//	go run . ../../tests/conformance/expressions/eval.json ../../tests/conformance/expressions/check.json
package main

import (
	"encoding/json"
	"fmt"
	"os"
	"slices"
	"strconv"
	"strings"

	"cel.dev/cel-go/cel"
	"cel.dev/cel-go/common/types"
)

type fixture struct {
	Cases []struct {
		ID       string         `json:"id"`
		Expr     string         `json:"expr"`
		Bindings map[string]any `json:"bindings"`
		Expect   map[string]any `json:"expect"`
	} `json:"cases"`
}

// allowedDivergences lists cases where ACS is deliberately stricter than CEL:
// ACS reports an evaluation error and CEL returns a value. None exist today;
// any addition needs a STANDARD change that names it.
var allowedDivergences = map[string]string{}

// hoist replaces every ${...} outside string literals with a fresh variable
// name, calling bind with the reference body. Inside a string literal
// `${` is data, as in ACS.
func hoist(src string, bind func(body string) string) string {
	var out strings.Builder
	for i := 0; i < len(src); {
		switch {
		case src[i] == '"':
			j := i + 1
			for j < len(src) && src[j] != '"' {
				if src[j] == '\\' {
					j++
				}
				j++
			}
			end := min(j+1, len(src))
			out.WriteString(src[i:end])
			i = end
		case strings.HasPrefix(src[i:], "${"):
			close := strings.IndexByte(src[i:], '}')
			if close < 0 {
				out.WriteString(src[i:])
				i = len(src)
				continue
			}
			out.WriteString(bind(src[i+2 : i+close]))
			i += close + 1
		default:
			out.WriteByte(src[i])
			i++
		}
	}
	return out.String()
}

type segment struct {
	field      string
	index      int
	slice      bool
	start, end *int
	isIndex    bool
}

// parseRef parses "root.a[0][1:2]: type" into a root and segments; the type
// annotation is static only and has no runtime effect.
func parseRef(body string) (string, []segment, error) {
	depth := 0
	cut := len(body)
	for i, c := range body {
		switch c {
		case '[':
			depth++
		case ']':
			depth--
		case ':':
			if depth == 0 && cut == len(body) {
				cut = i
			}
		}
	}
	p := strings.TrimSpace(body[:cut])
	identEnd := func(s string) int {
		for i, c := range s {
			if !(c == '_' || c == '-' || c >= '0' && c <= '9' || c >= 'a' && c <= 'z' || c >= 'A' && c <= 'Z') {
				return i
			}
		}
		return len(s)
	}
	n := identEnd(p)
	if n == 0 {
		return "", nil, fmt.Errorf("bad reference %q", body)
	}
	root, rest := p[:n], p[n:]
	var segs []segment
	for rest != "" {
		switch rest[0] {
		case '.':
			m := identEnd(rest[1:])
			segs = append(segs, segment{field: rest[1 : 1+m]})
			rest = rest[1+m:]
		case '[':
			close := strings.IndexByte(rest, ']')
			inner := rest[1:close]
			if a, b, ok := strings.Cut(inner, ":"); ok {
				s := segment{slice: true}
				if a != "" {
					v, _ := strconv.Atoi(a)
					s.start = &v
				}
				if b != "" {
					v, _ := strconv.Atoi(b)
					s.end = &v
				}
				segs = append(segs, s)
			} else {
				v, _ := strconv.Atoi(inner)
				segs = append(segs, segment{index: v, isIndex: true})
			}
			rest = rest[close+1:]
		default:
			return "", nil, fmt.Errorf("bad reference %q", body)
		}
	}
	return root, segs, nil
}

// resolve mirrors the ACS runtime: a missing root or key, an index out of
// range, or a segment on the wrong kind of value is null; slices clamp.
func resolve(v any, segs []segment) any {
	for _, s := range segs {
		switch {
		case s.slice:
			arr, ok := v.([]any)
			if !ok {
				return nil
			}
			n := len(arr)
			a, b := 0, n
			if s.start != nil {
				a = min(*s.start, n)
			}
			if s.end != nil {
				b = min(*s.end, n)
			}
			if a >= b {
				v = []any{}
			} else {
				v = arr[a:b]
			}
		case s.isIndex:
			arr, ok := v.([]any)
			if !ok || s.index >= len(arr) {
				return nil
			}
			v = arr[s.index]
		default:
			m, ok := v.(map[string]any)
			if !ok {
				return nil
			}
			v = m[s.field]
		}
	}
	return v
}

type checkFixture struct {
	Cases []struct {
		ID     string   `json:"id"`
		Expr   string   `json:"expr"`
		Expect []string `json:"expect"`
	} `json:"cases"`
}

func load(path string, into any) {
	raw, err := os.ReadFile(path)
	if err == nil {
		err = json.Unmarshal(raw, into)
	}
	if err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(2)
	}
}

// checkSyntax parses every ACS-valid check.json expression as CEL.
func checkSyntax(path string) int {
	var fx checkFixture
	load(path, &fx)
	failures, parsed := 0, 0
	for _, c := range fx.Cases {
		if slices.Contains(c.Expect, "V108") || slices.Contains(c.Expect, "B205") {
			continue
		}
		var opts []cel.EnvOption
		i := 0
		hoisted := hoist(c.Expr, func(body string) string {
			name := fmt.Sprintf("__r%d", i)
			i++
			opts = append(opts, cel.Variable(name, cel.DynType))
			return name
		})
		env, err := cel.NewEnv(opts...)
		if err == nil {
			_, iss := env.Parse(hoisted)
			err = iss.Err()
		}
		parsed++
		if err != nil {
			fmt.Printf("FAIL %s: valid ACS but not valid CEL: %q: %v\n", c.ID, hoisted, err)
			failures++
		}
	}
	fmt.Printf("parsed %d check.json expressions as CEL, %d failures\n", parsed, failures)
	return failures
}

func main() {
	if len(os.Args) != 3 {
		fmt.Fprintln(os.Stderr, "usage: cel_differential path/to/eval.json path/to/check.json")
		os.Exit(2)
	}
	var fx fixture
	load(os.Args[1], &fx)

	failures, compared, skipped := 0, 0, 0
	for _, c := range fx.Cases {
		if c.Expect["error"] == "V108" {
			skipped++ // not ACS: the one-way contract says nothing about it
			continue
		}
		vars := map[string]any{}
		var opts []cel.EnvOption
		i := 0
		hoisted := hoist(c.Expr, func(body string) string {
			root, segs, err := parseRef(body)
			if err != nil {
				return "${" + body + "}" // left as is; parsing fails and is reported
			}
			name := fmt.Sprintf("__r%d", i)
			i++
			vars[name] = resolve(c.Bindings[root], segs)
			opts = append(opts, cel.Variable(name, cel.DynType))
			return name
		})
		opts = append(opts, cel.CrossTypeNumericComparisons(true))
		env, err := cel.NewEnv(opts...)
		if err != nil {
			fmt.Printf("FAIL %s: environment: %v\n", c.ID, err)
			failures++
			continue
		}
		// Parse without type-checking: CEL's checker rejects comparisons of
		// literals of different types, but its runtime semantics — what ACS
		// promises to match — are defined for them.
		ast, iss := env.Parse(hoisted)
		if iss.Err() != nil {
			fmt.Printf("FAIL %s: valid ACS but not valid CEL: %q: %v\n", c.ID, hoisted, iss.Err())
			failures++
			continue
		}
		prg, err := env.Program(ast)
		if err != nil {
			fmt.Printf("FAIL %s: program: %v\n", c.ID, err)
			failures++
			continue
		}
		out, _, evalErr := prg.Eval(vars)
		compared++
		acsValue, acsHasValue := c.Expect["value"]
		celHasValue := evalErr == nil && !types.IsError(out)
		switch {
		case !celHasValue:
			// CEL errors: ACS may return a value only where CEL's error is
			// absorbed differently, which the absorption rule forbids.
			if acsHasValue {
				fmt.Printf("FAIL %s: ACS gives %v but CEL errors (%v)\n", c.ID, acsValue, evalErr)
				failures++
			}
		case acsHasValue:
			if out.Value() != acsValue {
				fmt.Printf("FAIL %s: ACS gives %v but CEL gives %v for %q\n", c.ID, acsValue, out.Value(), hoisted)
				failures++
			}
		default:
			// A condition must be boolean; CEL leaves that to its host.
			if _, isBool := out.Value().(bool); !isBool {
				continue
			}
			if why, ok := allowedDivergences[c.ID]; ok {
				fmt.Printf("ok   %s: documented divergence (%s)\n", c.ID, why)
				continue
			}
			fmt.Printf("FAIL %s: ACS errors but CEL gives %v for %q\n", c.ID, out.Value(), hoisted)
			failures++
		}
	}
	fmt.Printf("\ncompared %d cases, skipped %d invalid-in-ACS cases, %d failures\n", compared, skipped, failures)
	failures += checkSyntax(os.Args[2])
	if failures > 0 {
		os.Exit(1)
	}
}
