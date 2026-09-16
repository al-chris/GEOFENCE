#!/usr/bin/env python3
"""Independent verification of ``geofence_lawnmower.kicad_sch``.

This does not import the generator: it re-parses the emitted file from scratch
and re-derives every pin position using KiCad's real placement transform

    screen = instance_origin + (local_x, -local_y)

so that a bug in the generator cannot hide behind the same assumption in the
checker.

Exit code 0 = every check passed.
"""

from __future__ import annotations

import re
import sys
from collections import defaultdict, Counter

FILE = "geofence_lawnmower.kicad_sch"
GRID = 1.27
EPS = 1e-4

POWER_NETS = {"+5V", "GND", "+VMOTOR"}

# Reference designators whose terminals are identified by physical pin number
# rather than pin name: WIRING.md addresses the Raspberry Pi header that way
# ("Pin 11 / GPIO 17"), and its pin names repeat (GND x8, 5V x2, 3V3 x2).
NUMBER_IDENTIFIED = {"J1"}

# Reference netlist this schematic is required to produce.  Terminals are
# "<ref>.<pin name>" where the name is unique on that symbol, and
# "<ref>.<pin number>" where it is not (J1 has eight GND pins, two 5V pins, ...).
EXPECTED = {
    "+5V": {"J1.2", "U1.VCC", "U2.VCC", "U_L.VCC", "U_R.VCC",
            "C1.1", "C2.1", "C3.1", "C4.1"},
    "GND": {"J1.6", "J1.9", "J1.14", "J1.20", "J1.25", "J1.30", "J1.34", "J1.39",
            "U1.GND", "U2.GND", "U_L.GND", "U_R.GND", "U_L.B-", "U_R.B-",
            "BT1.-", "C1.2", "C2.2", "C3.2", "C4.2", "BZ1.-", "D1.K", "D2.K",
            "R4.2"},
    "+VMOTOR": {"U_L.B+", "U_R.B+", "F1.2"},
    "GPIO14_TXD": {"J1.8", "U1.RXD"},
    "GPIO15_RXD": {"J1.10", "U1.TXD"},
    "GPIO17_BUZZER": {"J1.11", "BZ1.+"},
    "GPIO27_LED_RED": {"J1.13", "R1.1"},
    "GPIO22_LED_GRN": {"J1.15", "R2.1"},
    "GPIO23_TRIG": {"J1.16", "U2.TRIG"},
    "GPIO24_ECHO": {"J1.18", "R3.2", "R4.1"},
    "GPIO12_L_RPWM": {"J1.32", "U_L.RPWM"},
    "GPIO13_L_LPWM": {"J1.33", "U_L.LPWM"},
    "GPIO20_L_REN": {"J1.38", "U_L.R_EN"},
    "GPIO21_L_LEN": {"J1.40", "U_L.L_EN"},
    "GPIO18_R_RPWM": {"J1.12", "U_R.RPWM"},
    "GPIO19_R_LPWM": {"J1.35", "U_R.LPWM"},
    "GPIO16_R_REN": {"J1.36", "U_R.R_EN"},
    "GPIO26_R_LEN": {"J1.37", "U_R.L_EN"},
}

# terminals that must be tied together but carry no net label
EXPECTED_UNLABELLED = [
    {"R1.2", "D1.A"},          # red LED series resistor
    {"R2.2", "D2.A"},          # green LED series resistor
    {"U_L.M+", "M_L.+"},
    {"U_L.M-", "M_L.-"},
    {"U_R.M+", "M_R.+"},
    {"U_R.M-", "M_R.-"},
    {"BT1.+", "F1.1"},         # battery -> fuse
]

EXPECTED_NC = {
    "J1.1", "J1.3", "J1.4", "J1.5", "J1.7", "J1.17", "J1.19", "J1.21",
    "J1.22", "J1.23", "J1.24", "J1.26", "J1.27", "J1.28", "J1.29", "J1.31",
    "U_L.R_IS", "U_L.L_IS", "U_R.R_IS", "U_R.L_IS",
}

failures: list[str] = []
warnings: list[str] = []


def fail(msg):
    failures.append(msg)


def warn(msg):
    warnings.append(msg)


# --------------------------------------------------------------------------- #
# parse
# --------------------------------------------------------------------------- #
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
            else:
                node.append(t)
        return node

    assert next(it) == "("
    return build()


def kids(node, key):
    return [c for c in node if isinstance(c, list) and c and c[0] == key]


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


src = open(FILE, encoding="utf-8").read()

# --- check 1: balanced parentheses ---------------------------------------- #
depth = 0
in_str = False
prev = ""
for ch in src:
    if ch == '"' and prev != "\\":
        in_str = not in_str
    elif not in_str:
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
            if depth < 0:
                fail("unbalanced parentheses (extra ')')")
                break
    prev = ch
if depth != 0:
    fail(f"unbalanced parentheses (depth {depth} at EOF)")

root = parse(tokenize(src))

# --------------------------------------------------------------------------- #
# library symbols
# --------------------------------------------------------------------------- #
lib = {}
for holder in kids(root, "lib_symbols"):
    for sym in kids(holder, "symbol"):
        name = unq(sym[1])
        pins, gfx, names = {}, [], []
        for p in find_all(sym, "pin"):
            at = kids(p, "at")[0]
            num = unq(kids(p, "number")[0][1])
            pname = unq(kids(p, "name")[0][1])
            pins[num] = (float(at[1]), float(at[2]), pname)
            names.append(pname)
        for g in kids(sym, "symbol"):
            for prim in g:
                if isinstance(prim, list) and prim[0] in ("rectangle", "polyline", "circle"):
                    gfx.append(prim)
        lib[name] = {"pins": pins, "gfx": gfx, "names": names}

if not lib:
    fail("no lib_symbols parsed")

# --------------------------------------------------------------------------- #
# instances -> pin screen positions (KiCad transform: y negated)
# --------------------------------------------------------------------------- #
def prim_extent(prim):
    if prim[0] == "rectangle":
        s, e = kids(prim, "start")[0], kids(prim, "end")[0]
        return [(float(s[1]), float(s[2])), (float(e[1]), float(e[2]))]
    if prim[0] == "polyline":
        return [(float(xy[1]), float(xy[2])) for xy in kids(kids(prim, "pts")[0], "xy")]
    if prim[0] == "circle":
        c, r = kids(prim, "center")[0], float(kids(prim, "radius")[0][1])
        cx, cy = float(c[1]), float(c[2])
        return [(cx - r, cy - r), (cx + r, cy + r)]
    return []


pins = {}          # terminal label -> (x, y)
term_by_num = {}   # "<ref>.<pin number>" -> terminal label
symbols = []       # (ref, value, x, y, bbox)
refs = []

for sym in kids(root, "symbol"):
    lid = kids(sym, "lib_id")[0]
    libname = unq(lid[1])
    at = kids(sym, "at")[0]
    X, Y = float(at[1]), float(at[2])
    ref = next((unq(p[2]) for p in kids(sym, "property") if unq(p[1]) == "Reference"), "?")
    val = next((unq(p[2]) for p in kids(sym, "property") if unq(p[1]) == "Value"), "?")
    refs.append(ref)

    # A pin name is only usable as an identifier when it is unique on the
    # symbol; the 40-pin header repeats GND/5V/3V3 many times, so those pins
    # have to be identified by number instead.
    name_count = Counter(lib[libname]["names"])

    def term(num, pname):
        if ref not in NUMBER_IDENTIFIED and pname != "~" and name_count[pname] == 1:
            return f"{ref}.{pname}"
        return f"{ref}.{num}"

    pts = []
    for num, (lx, ly, pname) in lib[libname]["pins"].items():
        sx, sy = X + lx, Y - ly          # <-- KiCad's real transform
        t = term(num, pname)
        pins[t] = (round(sx, 4), round(sy, 4))
        term_by_num[f"{ref}.{num}"] = t
        pts.append((sx, sy))
    for prim in lib[libname]["gfx"]:
        for lx, ly in prim_extent(prim):
            pts.append((X + lx, Y - ly))
    if pts:
        xs_ = [p[0] for p in pts]
        ys_ = [p[1] for p in pts]
        symbols.append((ref, val, X, Y, (min(xs_), min(ys_), max(xs_), max(ys_))))

# --------------------------------------------------------------------------- #
# wires / labels / junctions / no-connects
# --------------------------------------------------------------------------- #
wires = []
for w in kids(root, "wire"):
    xy = kids(kids(w, "pts")[0], "xy")
    a = (round(float(xy[0][1]), 4), round(float(xy[0][2]), 4))
    b = (round(float(xy[1][1]), 4), round(float(xy[1][2]), 4))
    if a == b:
        fail(f"zero-length wire at {a}")
    wires.append((a, b))

labels = [(( round(float(k[0][1]), 4), round(float(k[0][2]), 4) ), unq(l[1]))
          for l in kids(root, "label") for k in [kids(l, "at")]]
junctions = [(round(float(k[1]), 4), round(float(k[2]), 4))
             for j in kids(root, "junction") for k in [kids(j, "at")[0]]]
ncs = [(round(float(k[1]), 4), round(float(k[2]), 4))
       for n in kids(root, "no_connect") for k in [kids(n, "at")[0]]]

pin_at = defaultdict(list)
for name, pt in pins.items():
    pin_at[pt].append(name)
label_at = defaultdict(list)
for pt, text in labels:
    label_at[pt].append(text)

# --- check: every wire endpoint lands on a pin, label, junction or NC ------ #
for a, b in wires:
    for end in (a, b):
        if not (pin_at.get(end) or label_at.get(end)
                or end in junctions or end in ncs):
            fail(f"dangling wire end at {end}")

# --- check: every pin is wired, or explicitly no-connected ---------------- #
wire_pts = {p for w in wires for p in w}
for name, pt in sorted(pins.items()):
    if pt in ncs:
        continue
    if pt not in wire_pts:
        fail(f"pin {name} at {pt} is neither wired nor marked no-connect")

# --- check: every no_connect flag sits on a real pin --------------------- #
for pt in ncs:
    if pt not in pin_at:
        fail(f"no_connect flag at {pt} is not on any pin")

# --- check: the no-connect set matches the declared one ------------------ #
nc_terms = {t for pt in ncs for t in pin_at.get(pt, [])}
if nc_terms != EXPECTED_NC:
    fail(f"no-connect set mismatch: unexpected {sorted(nc_terms - EXPECTED_NC)}, "
         f"not flagged {sorted(EXPECTED_NC - nc_terms)}")

# --- check: endpoints on the 1.27 mm grid --------------------------------- #
def off_grid(v):
    return abs(v / GRID - round(v / GRID)) > 1e-3


for pt in sorted(wire_pts | set(junctions) | set(ncs) | set(pin_at)):
    if off_grid(pt[0]) or off_grid(pt[1]):
        fail(f"off-grid connection point {pt}")
for pt in label_at:
    if off_grid(pt[0]) or off_grid(pt[1]):
        fail(f"off-grid label anchor {pt}")

# --- check: duplicate references ------------------------------------------ #
for r, c in Counter(refs).items():
    if c > 1:
        fail(f"duplicate reference designator {r} x{c}")

# --------------------------------------------------------------------------- #
# netlist: union-find over wire endpoints, then attach pins/labels
# --------------------------------------------------------------------------- #
parent = {}


def find(n):
    parent.setdefault(n, n)
    while parent[n] != n:
        parent[n] = parent[parent[n]]
        n = parent[n]
    return n


def union(a, b):
    ra, rb = find(a), find(b)
    if ra != rb:
        parent[ra] = rb


for a, b in wires:
    union(a, b)

net_of_pin = {}
for name, pt in pins.items():
    if pt in wire_pts:
        net_of_pin[name] = find(pt)

# assign net names from labels
net_name = defaultdict(set)
for pt, texts in label_at.items():
    if pt in wire_pts or pt in pin_at:
        r = find(pt)
        for t in texts:
            net_name[r].add(t)

# also: pins directly coincident with a label anchor but no wire
for pt, texts in label_at.items():
    for t in texts:
        if pt in pin_at:
            net_name[find(pt)].add(t)

# --------------------------------------------------------------------------- #
# compare against the expected netlist
# --------------------------------------------------------------------------- #
# Build a mapping weight -> set of pins. Terminals are "<ref>.<pinname>", and
# since unnamed pins are all "~" we have to qualify resistors/caps by reference.
by_net = defaultdict(set)
unlabelled = defaultdict(set)
for name, root_ in net_of_pin.items():
    names = net_name.get(root_)
    if names:
        for n in names:
            by_net[n].add(name)
    else:
        unlabelled[root_].add(name)

for net, want in EXPECTED.items():
    got = by_net.get(net, set())
    missing = {t for t in want if t not in got}
    extra = {t for t in got if t not in want}
    if missing:
        fail(f"net {net}: missing terminals {sorted(missing)}")
    if extra:
        fail(f"net {net}: unexpected terminals {sorted(extra)}")

for want in EXPECTED_UNLABELLED:
    if not any(want <= group for group in unlabelled.values()):
        fail(f"expected an unlabelled net containing exactly {sorted(want)}")

# every terminal on a labelled net must appear in EXPECTED (catch typos / swaps)
all_expected = set()
for s in EXPECTED.values():
    all_expected |= s
for s in EXPECTED_UNLABELLED:
    all_expected |= s
for net in by_net:
    if net not in EXPECTED:
        fail(f"net {net} exists but is not in the expected netlist")

# --------------------------------------------------------------------------- #
# geometry: symbol bounding boxes must not overlap
# --------------------------------------------------------------------------- #
for i in range(len(symbols)):
    for j in range(i + 1, len(symbols)):
        ra, va, _, _, (ax1, ay1, ax2, ay2) = symbols[i]
        rb, vb, _, _, (bx1, by1, bx2, by2) = symbols[j]
        if ax1 < bx2 - EPS and bx1 < ax2 - EPS and ay1 < by2 - EPS and by1 < ay2 - EPS:
            fail(f"symbols {ra} ({va}) and {rb} ({vb}) overlap")

# --------------------------------------------------------------------------- #
# geometry: text collisions between labels and reference/value fields
# --------------------------------------------------------------------------- #
def text_box(text, x, y, size, justify):
    w = len(text) * size * 0.95 + 0.6
    h = size * 1.35
    if "right" in justify:
        x1, x2 = x - w, x
    elif "center" in justify:
        x1, x2 = x - w / 2, x + w / 2
    else:
        x1, x2 = x, x + w
    if "bottom" in justify:
        y1, y2 = y - h, y
    elif "top" in justify:
        y1, y2 = y, y + h
    else:
        y1, y2 = y - h / 2, y + h / 2
    return (x1, y1, x2, y2)


texts = []
for l in kids(root, "label"):
    at = kids(l, "at")[0]
    eff = kids(l, "effects")[0]
    j = [t for t in kids(eff, "justify")[0][1:]] if kids(eff, "justify") else []
    texts.append((unq(l[1]), float(at[1]), float(at[2]), 1.27, " ".join(j)))
for t in kids(root, "text"):
    at = kids(t, "at")[0]
    eff = kids(t, "effects")[0]
    font = kids(eff, "font")[0]
    size = float(kids(font, "size")[0][1])
    j = [x for x in kids(eff, "justify")[0][1:]] if kids(eff, "justify") else ["center"]
    texts.append((unq(t[1]), float(at[1]), float(at[2]), size, " ".join(j)))
for sym in kids(root, "symbol"):
    for p in kids(sym, "property"):
        if unq(p[1]) not in ("Reference", "Value"):
            continue
        at = kids(p, "at")[0]
        eff = kids(p, "effects")[0]
        j = [x for x in kids(eff, "justify")[0][1:]] if kids(eff, "justify") else ["center"]
        texts.append((unq(p[2]), float(at[1]), float(at[2]), 1.27, " ".join(j)))

boxes = [text_box(*t) for t in texts]
for i in range(len(texts)):
    for j in range(i + 1, len(texts)):
        a, b = boxes[i], boxes[j]
        if a[0] < b[2] - EPS and b[0] < a[2] - EPS and \
           a[1] < b[3] - EPS and b[1] < a[3] - EPS:
            warn(f"text overlap: {texts[i][0]!r} with {texts[j][0]!r}")

# --------------------------------------------------------------------------- #
# geometry: nothing may sit on the worksheet title block or outside the frame
# --------------------------------------------------------------------------- #
# A2 = 594 x 420 mm.  KiCad's default worksheet puts the drawing frame 10 mm in
# from each edge and anchors the title block to the bottom-right corner; the
# kicanvas drawing-sheet model reports it as a 110 x 34 mm box 2 mm in from
# that corner.
PAGE_W, PAGE_H = 594, 420
FRAME = (10, 10, PAGE_W - 10, PAGE_H - 10)
TITLE_BLOCK = (PAGE_W - 110, PAGE_H - 34, PAGE_W - 2, PAGE_H - 2)


def overlaps(a, b):
    return a[0] < b[2] - EPS and b[0] < a[2] - EPS and \
           a[1] < b[3] - EPS and b[1] < a[3] - EPS


drawn = []
for ref, val, _, _, bbox in symbols:
    drawn.append((f"symbol {ref} ({val})", bbox))
for r in kids(root, "rectangle"):
    s = kids(r, "start")[0]
    e = kids(r, "end")[0]
    x1, y1, x2, y2 = float(s[1]), float(s[2]), float(e[1]), float(e[2])
    drawn.append(("zone box", (min(x1, x2), min(y1, y2), max(x1, x2), max(y1, y2))))
for t in kids(root, "text"):
    at = kids(t, "at")[0]
    eff = kids(t, "effects")[0]
    size = float(kids(kids(eff, "font")[0], "size")[0][1])
    drawn.append((f"text {unq(t[1])[:28]!r}",
                  text_box(unq(t[1]), float(at[1]), float(at[2]), size, "left")))
for name, (x, y) in pins.items():
    drawn.append((f"pin {name}", (x - 0.3, y - 0.3, x + 0.3, y + 0.3)))

for what, box in drawn:
    if overlaps(box, TITLE_BLOCK):
        fail(f"{what} overlaps the worksheet title block at {tuple(round(v, 1) for v in box)}")
    if box[0] < FRAME[0] - EPS or box[1] < FRAME[1] - EPS or \
       box[2] > FRAME[2] + EPS or box[3] > FRAME[3] + EPS:
        fail(f"{what} falls outside the drawing frame at "
             f"{tuple(round(v, 1) for v in box)}")

# --------------------------------------------------------------------------- #
# report
# --------------------------------------------------------------------------- #
print(f"file            : {FILE} ({len(src)} bytes)")
print(f"lib symbols     : {len(lib)}")
print(f"placed symbols  : {len(symbols)}")
print(f"pins            : {len(pins)}")
print(f"wires           : {len(wires)}")
print(f"labels          : {len(labels)}")
print(f"junctions       : {len(junctions)}")
print(f"no_connects     : {len(ncs)}")
print()
print("--- extracted netlist ---")
for net in sorted(by_net):
    print(f"  {net:<16} {' '.join(sorted(by_net[net]))}")
print("  (unlabelled locals)")
for group in unlabelled.values():
    if len(group) > 1:
        print(f"  {'':<16} {' '.join(sorted(group))}")
print()

if warnings:
    print(f"--- {len(warnings)} warning(s) ---")
    for w in warnings:
        print(f"  ! {w}")
    print()

if failures:
    print(f"FAILED ({len(failures)} problem(s)):")
    for f in failures:
        print(f"  x {f}")
    sys.exit(1)

print("ALL CHECKS PASSED")
