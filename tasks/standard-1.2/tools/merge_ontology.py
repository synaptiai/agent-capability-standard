"""Apply every workstream's ontology 2.2.0 delta (as the reconciled designs state
them) to schemas/capability_ontology.yaml and print the merged contracts of the
nodes that change beyond S4's templates. Used to write FOUNDATION.md part A and
to check the result loads. Run: python3 merge_ontology.py REPO DESIGNS [--write OUT]"""
import copy, sys, textwrap, pathlib, yaml
sys.path.insert(0, str(pathlib.Path(__file__).parent))
from blocks import blocks

repo, designs = pathlib.Path(sys.argv[1]), pathlib.Path(sys.argv[2])
onto = yaml.safe_load((repo / "schemas/capability_ontology.yaml").read_text())
nodes = {n["id"]: n for n in onto["nodes"]}
def y(text): return yaml.safe_load(textwrap.dedent(text))
def B(name, a, b): return [y(body) for _, _, body in blocks(designs / name, a, b)]

s2b = B("S2b.md", r"^### 3.1 Ontology", r"^### 3.2 ")
s3 = B("S3.md", r"^### 3.1 Ontology", r"^### 3.2 ")
s4 = B("S4.md", r"^### 3.1 Ontology", r"^### 3.2 ")
s5 = B("S5.md", r"^### 3.1 Ontology", r"^### 3.2 ")
s6 = B("S6.md", r"^### 3.1 Ontology", r"^### 3.2 ")

def insert_after(d, after, new):
    out = {}
    for k, v in d.items():
        out[k] = v
        if k == after:
            out.update(new)
    if after not in d:
        out.update(new)
    return out

# --- S2b: audit (whole input/output) ---
audit = nodes["audit"]; audit.update(s2b[0])
# --- S5: checkpoint, rollback, send, persist, recall, delegate.effective.checkpointed ---
nodes["checkpoint"].update(s5[0]); nodes["rollback"].update(s5[1])
nodes["send"]["input_schema"]["properties"].update(s5[2])          # destination description
nodes["send"]["output_schema"] = s5[3]["output_schema"]
nodes["persist"].update(s5[4]); nodes["recall"].update(s5[5])
eff = nodes["delegate"]["output_schema"]["properties"]["effective"]["properties"]
nodes["delegate"]["output_schema"]["properties"]["effective"]["properties"] = insert_after(eff, "read_only", s5[6])
# --- S3: delegate inputs/outputs, inquire, receive, conflicts_with ---
dp = nodes["delegate"]["input_schema"]["properties"]
dp["agent"] = s3[0]["agent"]; dp["model_family"] = s3[0]["model_family"]
dp["read_only"] = s3[1]["read_only"]
nodes["delegate"]["input_schema"]["properties"] = insert_after(dp, "read_only", {"continues": s3[0]["continues"]})
eff = nodes["delegate"]["output_schema"]["properties"]["effective"]["properties"]
eff["model_family"] = s3[2]["model_family"]
nodes["delegate"]["output_schema"]["properties"]["effective"]["properties"] = insert_after(eff, "model_family", {"model_id": s3[2]["model_id"]})
iq = nodes["inquire"]["output_schema"]["properties"]
iq = {"inquiry_id": s3[3]["inquiry_id"], **iq}; iq["questions"] = s3[3]["questions"]
nodes["inquire"]["output_schema"]["properties"] = iq
items = nodes["receive"]["output_schema"]["properties"]["data"]["items"]["properties"]
items.update(s3[4])
onto["edge_types"]["conflicts_with"].update(s3[5]["conflicts_with"])
# --- S6: integrate.conflict_resolution description ---
nodes["integrate"]["input_schema"]["properties"]["conflict_resolution"] = s6[0][0]["input_schema"]["properties"]["conflict_resolution"]
# --- S4: principles, templates, measure.uncertainty, audit retention/store ---
onto["meta"]["principles"] = s4[0]["principles"]
A, Bc, Cc, D, E = s4[1]["evidence_anchors"], s4[2]["confidence"], s4[3]["confidence"], s4[4]["inference_method"], s4[5]["uncertainty"]
REQ_CONF = "retrieve search observe detect classify measure predict compare discover plan decompose critique explain state transition attribute ground simulate generate transform integrate verify inquire".split()
NO_CONF = "receive execute mutate send checkpoint rollback constrain audit persist recall delegate synchronize invoke".split()
assert len(REQ_CONF) == 23 and len(NO_CONF) == 13 and set(REQ_CONF) | set(NO_CONF) == set(nodes)
for cid, n in nodes.items():
    props = n["output_schema"]["properties"]
    old = props.get("evidence_anchors", {})
    a = copy.deepcopy(A)
    if "description" in old:
        a["description"] = old["description"] + " (Standard v1.2 §6.5)."
    props["evidence_anchors"] = a
    if cid in REQ_CONF:
        c = copy.deepcopy(Bc)
        if cid == "inquire":
            c["description"] = props["confidence"]["description"] + " (Standard v1.2 §4.1.1)"
        props["confidence"] = c
    else:
        assert "confidence" not in props, cid
        props["confidence"] = copy.deepcopy(Cc)
    props["inference_method"] = copy.deepcopy(D)
    if cid != "measure":
        props["uncertainty"] = copy.deepcopy(E)
nodes["measure"]["output_schema"]["properties"]["uncertainty"] = s4[6]["uncertainty"]
ai = nodes["audit"]["input_schema"]["properties"]; ai["retention"] = s4[7]["retention"]
ao = nodes["audit"]["output_schema"]["properties"]
nodes["audit"]["output_schema"]["properties"] = insert_after(ao, "record", {"store": s4[8]["store"]})
onto["meta"]["version"] = "2.2.0"
# required lists must be unchanged
orig = {n["id"]: n for n in yaml.safe_load((repo / "schemas/capability_ontology.yaml").read_text())["nodes"]}
for cid in nodes:
    for side in ("input_schema", "output_schema"):
        assert nodes[cid][side].get("required") == orig[cid][side].get("required"), (cid, side)
        missing = set(orig[cid][side].get("properties", {})) - set(nodes[cid][side].get("properties", {}))
        assert not missing, (cid, side, missing)
if "--write" in sys.argv:
    out = pathlib.Path(sys.argv[sys.argv.index("--write") + 1])
    out.write_text(yaml.safe_dump(onto, sort_keys=False, allow_unicode=True, width=88))
    print("wrote", out)
SHOW = ["audit", "checkpoint", "rollback", "send", "persist", "recall", "delegate", "inquire", "receive", "measure"]
if "--show" in sys.argv:
    TPL = {"A": A, "B": Bc, "C": Cc, "D": D, "E": E}
    def mark(props):
        out = {}
        for k, v in props.items():
            tag = next((n for n, tv in TPL.items() if v == tv), None)
            out[k] = f"<Template {tag}>" if tag else v
        return out
    for cid in SHOW:
        n = copy.deepcopy(nodes[cid])
        n["output_schema"]["properties"] = mark(n["output_schema"]["properties"])
        print(yaml.safe_dump([{"id": cid, "input_schema": n["input_schema"], "output_schema": n["output_schema"]}], sort_keys=False, allow_unicode=True, width=88))
    print(yaml.safe_dump({"conflicts_with": onto["edge_types"]["conflicts_with"]}, sort_keys=False, allow_unicode=True, width=88))
print("ok: ontology merged; required lists and existing properties preserved")
