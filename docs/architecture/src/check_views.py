"""Check that each per-view diagram agrees with the full diagram (verification master).

For every edge in a view: the full diagram has an edge with the same id, source, target,
label and style (exit/entry points excluded, since they are layout).
For every vertex in a view (title and legend excluded): the full diagram has the same id with the same label.

usage: python3 check_views.py <full.drawio> <view.drawio> [<view.drawio> ...]
exit code: 0 = no mismatch, 1 = mismatch found, 2 = usage error
"""
import re
import sys
import xml.etree.ElementTree as ET

LAYOUT_KEYS = re.compile(r"(exit|entry)(X|Y|Dx|Dy|Perimeter)=[^;]*;")


def load(path):
    cells = {}
    for c in ET.parse(path).iter("mxCell"):
        cid = c.get("id")
        if cid in ("0", "1"):
            continue
        cells[cid] = {
            "edge": c.get("edge") == "1",
            "source": c.get("source"),
            "target": c.get("target"),
            "value": c.get("value") or "",
            "style": LAYOUT_KEYS.sub("", c.get("style") or ""),
        }
    return cells


def is_view_specific(cid):
    return cid == "title" or cid.startswith("lg")


def main(argv):
    if len(argv) < 3:
        print("usage: python3 check_views.py <full.drawio> <view.drawio> [<view.drawio> ...]")
        return 2
    full = load(argv[1])
    bad = 0
    for path in argv[2:]:
        view = load(path)
        name = path.rsplit("/", 1)[-1]
        edges = 0
        for cid, c in view.items():
            if is_view_specific(cid):
                continue
            f = full.get(cid)
            if f is None:
                print("%s: %s is missing in the full diagram" % (name, cid))
                bad += 1
                continue
            keys = ("edge", "source", "target", "value", "style") if c["edge"] else ("edge", "value")
            for k in keys:
                if c[k] != f[k]:
                    print("%s: %s %s differs: view=%r full=%r" % (name, cid, k, c[k], f[k]))
                    bad += 1
            edges += c["edge"]
        print("%s: %d edges checked" % (name, edges))
    print("mismatches: %d" % bad)
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
