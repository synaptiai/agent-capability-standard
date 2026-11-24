import re, pathlib, collections, json
D = pathlib.Path("designs")
pat = re.compile(r"`((?:core|grounded_agency|examples|tests|scripts|tools|hooks|skills|schemas|spec|docs|packages|site|benchmarks|templates|\.github)/[A-Za-z0-9_./*{},-]+|CLAUDE\.md|README\.md|CHANGELOG\.md)`")
def norm(p):
    p = p.rstrip(".,")
    return p
res = {}
for s in ["S1","S2a","S2b","S3","S4","S5","S6"]:
    t = (D/f"{s}.md").read_text()
    # implementation, tests and docs parts only (5., 6., 7.) plus file lists
    m = re.search(r"\n## 5\. Implementation plan", t)
    m9 = re.search(r"\n## 8\. Backward", t)
    seg = t[m.start(): m9.start()] if m and m9 else t
    res[s] = sorted({norm(x) for x in pat.findall(seg)})
cnt = collections.defaultdict(list)
for s, fs in res.items():
    for f in fs: cnt[f].append(s)
shared = {f: ss for f, ss in cnt.items() if len(ss) > 1}
json.dump({"by_stream": res, "shared": shared}, open("files.json","w"), indent=1)
for f, ss in sorted(shared.items(), key=lambda x: (-len(x[1]), x[0])):
    print(f"{f}: {' '.join(ss)}")
