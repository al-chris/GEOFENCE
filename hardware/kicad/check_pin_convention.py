#!/usr/bin/env python3
"""Confirm how KiCad maps symbol-library coordinates onto schematic space.

A ``.kicad_sch`` stores its embedded ``lib_symbols`` geometry Y-**up**, but
schematic coordinates are Y-**down**, so an unrotated, unmirrored symbol
instance is drawn with

    screen = instance_origin + (local_x, -local_y)        # transform [1,0,0,-1]

If you lay a symbol out assuming ``+local_y`` instead, every symbol ends up
mirrored about its own origin and none of the wires touch their pins — while a
generator and a checker that share that assumption will happily agree with each
other.  So verify the convention against real KiCad files, not against your own
code.

This script downloads upstream KiCad demo schematics, and for every pin whose
local Y is non-zero checks whether the pin lands on a real wire endpoint under
the negated-Y rule or under the naive ``+local_y`` rule.  Vertically
self-symmetric parts (R, C, L, D, ...) are skipped: both rules predict the same
point set for them, so they carry no signal.

Expected result: the negated-Y rule wins overwhelmingly (0 hits for the naive
rule is ideal).  Requires network access.
"""

import urllib.request

BASE = "https://raw.githubusercontent.com/kicad/kicad-source-mirror/master/"
DEMOS = [
    "demos/pic_programmer/pic_programmer.kicad_sch",
    "demos/complex_hierarchy/complex_hierarchy.kicad_sch",
    "demos/kit-dev-coldfire-xilinx_5213/kit-dev-coldfire-xilinx_5213.kicad_sch",
    "demos/simulation/laser_driver/laser_driver.kicad_sch",
]


# --- minimal S-expression reader ------------------------------------------- #
def tokenize(s):
    out, i, n = [], 0, len(s)
    while i < n:
        c = s[i]
        if c in "()":
            out.append(c); i += 1
        elif c == '"':
            j, buf = i + 1, []
            while j < n and s[j] != '"':
                if s[j] == "\\":
                    j += 1
                buf.append(s[j]); j += 1
            out.append('"' + "".join(buf) + '"'); i = j + 1
        elif c.isspace():
            i += 1
        else:
            j = i
            while j < n and not s[j].isspace() and s[j] not in '()"':
                j += 1
            out.append(s[i:j]); i = j
    return out


def parse(tokens):
    it = iter(tokens)

    def build():
        node = []
        for t in it:
            if t == "(":
                node.append(build())
            elif t == ")":
                return node
            node.append(t)
        return node

    assert next(it) == "("
    return build()


def find_all(node, key):
    res = []
    if isinstance(node, list):
        if node and node[0] == key:
            res.append(node)
        for c in node:
            res.extend(find_all(c, key))
    return res


def unq(s):
    return s[1:-1] if isinstance(s, str) and s.startswith('"') else s


def main():
    totals = {"flip": 0, "noflip": 0, "both": 0, "neither": 0}
    outliers = []

    for rel in DEMOS:
        try:
            raw = urllib.request.urlopen(BASE + rel, timeout=60).read().decode("utf-8", "replace")
        except Exception as exc:  # pragma: no cover - network dependent
            print(f"skip {rel}: {exc}")
            continue

        root = parse(tokenize(raw))

        lib = {}
        for holder in [c for c in root if isinstance(c, list) and c and c[0] == "lib_symbols"]:
            for sym in [c for c in holder if isinstance(c, list) and c and c[0] == "symbol"]:
                pins = {}
                for p in find_all(sym, "pin"):
                    at = find_all(p, "at")[0]
                    pins[unq(find_all(p, "number")[0][1])] = (float(at[1]), float(at[2]))
                lib[unq(sym[1])] = pins

        wires = set()
        for w in find_all(root, "wire"):
            for xy in [c for c in find_all(w, "pts")[0]
                       if isinstance(c, list) and c[0] == "xy"]:
                wires.add((round(float(xy[1]), 3), round(float(xy[2]), 3)))

        flip = noflip = 0
        for sym in [c for c in root if isinstance(c, list) and c and c[0] == "symbol"]:
            lib_id = next((unq(c[1]) for c in sym
                           if isinstance(c, list) and c[0] == "lib_id"), None)
            at = next((c for c in sym if isinstance(c, list) and c[0] == "at"), None)
            if not lib_id or not at or lib_id not in lib:
                continue
            if len(at) >= 5 and (at[3] != "0" or at[4] != "0"):
                continue                      # rotated / mirrored: out of scope
            pts = lib[lib_id]
            if not pts:
                continue
            coords = {(round(x, 3), round(y, 3)) for x, y in pts.values()}
            if coords == {(x, round(-y, 3)) for x, y in coords}:
                continue                      # vertically symmetric -> no signal
            X, Y = float(at[1]), float(at[2])
            for num, (px, py) in pts.items():
                if py == 0:
                    continue
                hit_f = (round(X + px, 3), round(Y - py, 3)) in wires
                hit_n = (round(X + px, 3), round(Y + py, 3)) in wires
                if hit_f and hit_n:
                    totals["both"] += 1
                elif hit_f:
                    totals["flip"] += 1
                    flip += 1
                elif hit_n:
                    totals["noflip"] += 1
                    noflip += 1
                    outliers.append((rel.split("/")[1], lib_id, num, (X, Y), (px, py)))
                else:
                    totals["neither"] += 1
        print(f"{rel:<60} negated-Y={flip:<4} naive=+Y={noflip}")

    print()
    print(f"pins matching ONLY the negated-Y rule : {totals['flip']}")
    print(f"pins matching ONLY the naive +Y rule  : {totals['noflip']}")
    print(f"pins matching both (symmetric)        : {totals['both']}")
    print(f"pins matching neither (unconnected)   : {totals['neither']}")

    if outliers:
        # A single stray wire endpoint can land on the mirror-image position by
        # coincidence, especially when a pin is genuinely unconnected, so these
        # are reported for judgement rather than treated as a failure on their
        # own.  What matters is that the negated-Y rule dominates.
        print("\nnaive-rule-only hits (inspect if the ratio looks unhealthy):")
        for rel, lib_id, num, origin, local in outliers:
            print(f"  {rel}: {lib_id} pin {num} at {origin} local {local}")

    if totals["flip"] <= totals["noflip"]:
        print("\nFAIL: the negated-Y rule does not dominate - convention unclear.")
        raise SystemExit(1)
    print(f"\nOK: negated-Y placement confirmed "
          f"({totals['flip']} vs {totals['noflip']}).")


if __name__ == "__main__":
    main()
