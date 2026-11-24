import re, sys, pathlib
def blocks(path, start_pat, end_pat):
    t = pathlib.Path(path).read_text().splitlines()
    s = next(i for i,l in enumerate(t) if re.search(start_pat, l))
    e = next(i for i,l in enumerate(t) if i > s and re.search(end_pat, l))
    out = []; label = None; i = s
    while i < e:
        l = t[i]
        if l.startswith("```yaml"):
            j = i + 1
            while not t[j].startswith("```"): j += 1
            out.append((label, i+1, "\n".join(t[i+1:j])))
            i = j + 1; continue
        if l.strip(): label = l.strip()[:110]
        i += 1
    return out
if __name__ == "__main__":
    for lab, ln, body in blocks(sys.argv[1], sys.argv[2], sys.argv[3]):
        print(f"--- line {ln}: {lab}")
