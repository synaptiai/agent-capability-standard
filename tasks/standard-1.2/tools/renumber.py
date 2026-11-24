import re, pathlib, sys
MAP = {"R412": "R408", "W623": "W618", "W624": "W619", "W627": "W620", "W628": "W621",
       "W629": "W622", "W630": "W623", "W637": "W624", "W638": "W625", "W639": "W626"}
pat = re.compile(r"\b(" + "|".join(MAP) + r")\b")
for p in sorted(pathlib.Path(sys.argv[1]).glob("S*.md")):
    t = p.read_text()
    n = len(pat.findall(t))
    p.write_text(pat.sub(lambda m: MAP[m.group(1)], t))
    print(p.name, n)
