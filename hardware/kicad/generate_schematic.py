#!/usr/bin/env python3
"""Generate ``geofence_lawnmower.kicad_sch`` from a declarative description.

Why this script exists
======================
Hand-editing S-expressions for a 20-symbol sheet is how you get a schematic
whose wires do not touch its pins.  Everything below is declared once, in a
single coordinate frame, and the emitter takes care of the file-format
subtleties.

Coordinate conventions (read this before changing anything)
-----------------------------------------------------------
* **Everything in this script is in SCREEN coordinates**: +X right, +Y *down*,
  millimetres, origin at the sheet's top-left.  That is the frame you reason in
  when laying out a schematic, and it is also the frame used by ``wire``,
  ``label``, ``junction``, ``no_connect``, ``text`` and ``rectangle`` in a
  ``.kicad_sch`` file.

* **Symbol-library geometry is stored Y-UP**, and KiCad draws an unrotated,
  unmirrored instance with

      screen = instance_origin + (local_x, -local_y)

  (equivalently, KiCad's placement transform is ``[1,0,0,-1]``).  Verified
  empirically against the KiCad demo projects -- over six demos, 48 pin/wire
  coincidences fit only the negated-Y rule versus 1 for the naive
  ``+local_y`` rule.  Run ``check_pin_convention.py`` to re-confirm.

  So :meth:`Sym.emit` negates every library pin/graphic Y (and negates pin
  angles), after which a pin's on-sheet position is simply

      instance_origin + pin.offset

  and no caller ever has to think about the flip again.

Sizing / print target
---------------------
This sheet is A2 but is expected to be printed on A4, i.e. at 50% linear scale.
Text is therefore sized at 3.0 mm so it lands at ~1.5 mm on A4 -- slightly
better than a native A4 KiCad schematic, whose default text is 1.27 mm.
Symbol bodies and pin pitches are scaled to match, because a schematic symbol
is a drawing convention, not a physical dimension.

Worksheet keep-out (measured from the renderer, not assumed)
------------------------------------------------------------
The drawing frame's inner border sits 10 mm in from each page edge, and KiCad's
title block is a fixed 108 x 32 mm rectangle anchored to the *frame's* bottom
right corner -- not the page corner.  On A2 that is x 473.5..582, y 375.9..408.
:data:`CONTENT_RIGHT` plus the row budget below keep everything clear of it.

Run ``python verify_schematic.py`` after regenerating: it re-derives every pin
position *from the emitted file* using that same transform and fails loudly on
dangling wires, unconnected pins, off-grid endpoints, overlapping symbols, text
overlaps, and anything under the title block.
"""

from __future__ import annotations

import uuid

OUT = "geofence_lawnmower.kicad_sch"
PROJECT = "geofence_lawnmower"
ROOT_UUID = "9ed750d8-e90f-4cb6-aa14-8059ae2348b4"

GRID = 1.27  # 50 mil

# --- page + print sizing --------------------------------------------------- #
PAGE = "A2"
PAGE_W, PAGE_H = 594, 420
FRAME = 10                                   # frame inner border inset
TITLE_BLOCK = (473.5, 375.9, 582.0, 408.0)   # measured keep-out

TXT = 3.0          # net labels and component references/values
TXT_PIN = 2.5      # pin names and numbers (secondary to the net names, and
                   # they have to fit inside a fixed-pitch symbol body)
TXT_ZONE = 5.0     # zone headings
TXT_TITLE = 6.0    # sheet title
TXT_SUB = 3.0      # sheet subtitle

# Every zone shares these outer edges so the drawing looks aligned, not ragged.
CONTENT_LEFT = 18.0
CONTENT_RIGHT = 470.0


# --------------------------------------------------------------------------- #
# formatting helpers
# --------------------------------------------------------------------------- #
def num(v: float) -> str:
    """Format a number the way KiCad does: no trailing zeros, no '+', no -0."""
    s = f"{v:.4f}".rstrip("0").rstrip(".")
    if s in ("-0", ""):
        s = "0"
    return s


def xs(v: float) -> str:
    """Round away float noise before formatting."""
    return num(round(v, 4))


def uid(*parts: str) -> str:
    """Deterministic UUID so regenerating produces a stable, reviewable diff."""
    return str(uuid.uuid5(uuid.NAMESPACE_URL, "geofence-kicad:" + ":".join(parts)))


# --------------------------------------------------------------------------- #
# symbol / pin model
# --------------------------------------------------------------------------- #
class Pin:
    """A pin, positioned in SCREEN offsets from the symbol origin.

    offset_x/offset_y is the *connection point* (the end the wire attaches to).
    ``angle`` is the SCREEN direction the pin extends in, i.e. from the
    connection point towards the symbol body:

        0 = +X   (pin on the left  side of a body)
      180 = -X   (pin on the right side of a body)
       90 = +Y   (pin on the top     of a body, body below it)
      270 = -Y   (pin on the bottom  of a body, body above it)
    """

    __slots__ = ("number", "name", "ox", "oy", "angle", "etype", "length")

    def __init__(self, number, name, ox, oy, angle, etype="passive", length=3.81):
        self.number = str(number)
        self.name = name
        self.ox = ox
        self.oy = oy
        self.angle = angle
        self.etype = etype
        self.length = length

    def emit(self) -> str:
        return (
            f"(pin {self.etype} line (at {xs(self.ox)} {xs(-self.oy)} "
            f"{xs((-self.angle) % 360)}) (length {xs(self.length)})\n"
            f'  (name "{self.name}" (effects (font (size {xs(TXT_PIN)} {xs(TXT_PIN)}))))\n'
            f'  (number "{self.number}" (effects (font (size {xs(TXT_PIN)} {xs(TXT_PIN)}))))\n'
            f")"
        )


class Sym:
    """A symbol definition: graphics + pins, all in SCREEN offsets."""

    def __init__(self, name, ref_prefix, graphics, pins, hide_pin_numbers=False):
        self.name = name
        self.ref_prefix = ref_prefix
        self.graphics = graphics
        self.pins = pins
        self.hide_pin_numbers = hide_pin_numbers

    def pin(self, number) -> Pin:
        for p in self.pins:
            if p.number == str(number):
                return p
        raise KeyError(f"{self.name}: no pin {number}")

    def emit(self) -> str:
        head = f'(symbol "GEO:{self.name}" (in_bom yes) (on_board yes)\n'
        if self.hide_pin_numbers:
            head += "  (pin_numbers hide)\n"
        body = "\n".join("  " + g.replace("\n", "\n  ") for g in self.graphics)
        pins = "\n".join("  " + p.emit().replace("\n", "\n  ") for p in self.pins)
        return (
            head
            + f'  (property "Reference" "{self.ref_prefix}" (at 0 0 0) '
            f"(effects (font (size {xs(TXT)} {xs(TXT)})) hide))\n"
            + f'  (property "Value" "{self.name}" (at 0 0 0) '
            f"(effects (font (size {xs(TXT)} {xs(TXT)})) hide))\n"
            + f'  (property "Footprint" "" (at 0 0 0) '
            f"(effects (font (size {xs(TXT)} {xs(TXT)})) hide))\n"
            + f'  (symbol "{self.name}_0_1"\n{body}\n  )\n'
            + f'  (symbol "{self.name}_1_1"\n{pins}\n  )\n'
            + ")"
        )


# --- graphic primitives (screen offsets, emitter negates Y) --------------- #
def rect(x1, y1, x2, y2, width=0.254):
    return (
        f"(rectangle (start {xs(x1)} {xs(-y1)}) (end {xs(x2)} {xs(-y2)}) "
        f"(stroke (width {xs(width)}) (type default)) (fill (type none)))"
    )


def circle(cx, cy, r, width=0.254):
    return (
        f"(circle (center {xs(cx)} {xs(-cy)}) (radius {xs(r)}) "
        f"(stroke (width {xs(width)}) (type default)) (fill (type none)))"
    )


def poly(points, width=0.254):
    pts = " ".join(f"(xy {xs(x)} {xs(-y)})" for x, y in points)
    return (
        f"(polyline (pts {pts}) "
        f"(stroke (width {xs(width)}) (type default)) (fill (type none)))"
    )


# --------------------------------------------------------------------------- #
# symbol definitions
#
# Pin pitch is 5.08 mm everywhere, so 3.0 mm text has comfortable clearance
# between adjacent pin names.  5.08 also keeps every row on the 1.27 mm grid
# while staying symmetric about the symbol origin (2.54 == 2 x 1.27).
# --------------------------------------------------------------------------- #
HEADER_ROWS = [
    (1, "3V3"), (2, "5V"), (3, "GPIO2_SDA"), (4, "5V"),
    (5, "GPIO3_SCL"), (6, "GND"), (7, "GPIO4"), (8, "GPIO14_TXD"),
    (9, "GND"), (10, "GPIO15_RXD"), (11, "GPIO17"), (12, "GPIO18"),
    (13, "GPIO27"), (14, "GND"), (15, "GPIO22"), (16, "GPIO23"),
    (17, "3V3"), (18, "GPIO24"), (19, "GPIO10_MOSI"), (20, "GND"),
    (21, "GPIO9_MISO"), (22, "GPIO25"), (23, "GPIO11_SCLK"), (24, "GPIO8_CE0"),
    (25, "GND"), (26, "GPIO7_CE1"), (27, "GPIO0_IDSD"), (28, "GPIO1_IDSC"),
    (29, "GPIO5"), (30, "GND"), (31, "GPIO6"), (32, "GPIO12"),
    (33, "GPIO13"), (34, "GND"), (35, "GPIO19"), (36, "GPIO16"),
    (37, "GPIO26"), (38, "GPIO20"), (39, "GND"), (40, "GPIO21"),
]

HDR_PITCH = 5.08
HDR_ROW0 = -48.26          # 19 rows at 5.08 -> +-48.26: symmetric and on grid
HDR_W2 = 38.1              # half body width: wide enough that the left- and
                           # right-hand pin names cannot meet in the middle
HDR_H2 = 53.34             # half body height
HDR_PINLEN = 5.08          # pins long enough to keep the pin numbers clear
                           # of both the body edge and the net labels


def _header_pins():
    pins = []
    for k, (number, name) in enumerate(HEADER_ROWS):
        oy = HDR_ROW0 + (k // 2) * HDR_PITCH
        left = number % 2 == 1
        etype = "power_out" if name in ("3V3", "5V") else (
            "passive" if name == "GND" else "bidirectional")
        pins.append(Pin(number, name,
                        -(HDR_W2 + HDR_PINLEN) if left else (HDR_W2 + HDR_PINLEN),
                        oy, 0 if left else 180, etype, HDR_PINLEN))
    return pins


SYMS = {}


def _add(sym):
    SYMS[sym.name] = sym


_add(Sym("RPI5_J8_HEADER", "J",
         [rect(-HDR_W2, -HDR_H2, HDR_W2, HDR_H2)],
         _header_pins()))

# 4-pin sensor modules: two pins per side, 10.16 apart.
_add(Sym("NEO_M8N_GPS", "U",
         [rect(-19.05, -12.7, 19.05, 12.7)],
         [Pin(1, "VCC", -22.86, -5.08, 0, "power_in"),
          Pin(2, "GND", -22.86, 5.08, 0, "passive"),
          Pin(3, "TXD", 22.86, -5.08, 180, "output"),
          Pin(4, "RXD", 22.86, 5.08, 180, "input")]))

_add(Sym("HC_SR04", "U",
         [rect(-19.05, -12.7, 19.05, 12.7)],
         [Pin(1, "VCC", -22.86, -5.08, 0, "power_in"),
          Pin(2, "GND", -22.86, 5.08, 0, "passive"),
          Pin(3, "TRIG", 22.86, -5.08, 180, "input"),
          Pin(4, "ECHO", 22.86, 5.08, 180, "output")]))

_add(Sym("BTS7960", "U",
         [rect(-25.4, -22.86, 25.4, 22.86)],
         [Pin(1, "VCC", -29.21, -17.78, 0, "power_in"),
          Pin(2, "GND", -29.21, -12.7, 0, "passive"),
          Pin(3, "RPWM", -29.21, -7.62, 0, "input"),
          Pin(4, "LPWM", -29.21, -2.54, 0, "input"),
          Pin(5, "R_EN", -29.21, 2.54, 0, "input"),
          Pin(6, "L_EN", -29.21, 7.62, 0, "input"),
          Pin(7, "R_IS", -29.21, 12.7, 0, "output"),
          Pin(8, "L_IS", -29.21, 17.78, 0, "output"),
          Pin(9, "B+", 29.21, -17.78, 180, "power_in"),
          Pin(10, "B-", 29.21, -7.62, 180, "power_in"),
          Pin(11, "M+", 29.21, 2.54, 180, "output"),
          Pin(12, "M-", 29.21, 12.7, 180, "output")]))

# Resistor: pin 1 on top, pin 2 on the bottom (the KiCad convention).
_add(Sym("R", "R",
         [rect(-2.54, -5.08, 2.54, 5.08)],
         [Pin(1, "~", 0, -7.62, 90, "passive", 2.54),
          Pin(2, "~", 0, 7.62, 270, "passive", 2.54)], hide_pin_numbers=True))

_add(Sym("C", "C",
         [poly([(-3.81, -1.27), (3.81, -1.27)], 0.508),
          poly([(-3.81, 1.27), (3.81, 1.27)], 0.508)],
         [Pin(1, "~", 0, -7.62, 90, "passive", 6.35),
          Pin(2, "~", 0, 7.62, 270, "passive", 6.35)], hide_pin_numbers=True))

# LED drawn pointing DOWN: anode (pin 1) on top, cathode (pin 2) below.
_add(Sym("LED", "D",
         [poly([(-2.54, -2.54), (2.54, -2.54), (0, 2.54), (-2.54, -2.54)]),
          poly([(-2.54, 2.54), (2.54, 2.54)], 0.508),
          poly([(3.81, -1.016), (6.604, -3.81)]),
          poly([(6.604, -3.81), (4.572, -3.556)]),
          poly([(6.604, -3.81), (6.35, -1.778)]),
          poly([(4.826, 1.524), (7.62, -1.27)]),
          poly([(7.62, -1.27), (5.588, -1.016)]),
          poly([(7.62, -1.27), (7.366, 0.762)])],
         [Pin(1, "A", 0, -7.62, 90, "passive", 5.08),
          Pin(2, "K", 0, 7.62, 270, "passive", 5.08)], hide_pin_numbers=True))

_add(Sym("BUZZER", "BZ",
         [circle(0, 0, 6.35)],
         [Pin(1, "+", 0, -7.62, 90, "passive", 1.27),
          Pin(2, "-", 0, 7.62, 270, "passive", 1.27)], hide_pin_numbers=True))

_add(Sym("DC_MOTOR", "M",
         [circle(0, 0, 12.7, 0.381)],
         [Pin(1, "+", -17.78, -5.08, 0, "passive", 7.62),
          Pin(2, "-", -17.78, 5.08, 0, "passive", 7.62)], hide_pin_numbers=True))

_add(Sym("BATTERY_PACK", "BT",
         [poly([(-8.89, -12.7), (8.89, -12.7)], 0.762),
          poly([(-4.572, -8.89), (4.572, -8.89)], 0.381),
          poly([(-8.89, -3.81), (8.89, -3.81)], 0.762),
          poly([(-4.572, 0.0), (4.572, 0.0)], 0.381),
          poly([(-8.89, 5.08), (8.89, 5.08)], 0.762),
          poly([(-4.572, 8.89), (4.572, 8.89)], 0.381)],
         # The pack is the source of the +VMOTOR rail, so its positive terminal
         # is a power_out - that is what stops ERC from reporting the BTS7960
         # B+ power_in pins as undriven.
         [Pin(1, "+", 0, -17.78, 90, "power_out", 5.08),
          Pin(2, "-", 0, 17.78, 270, "passive", 8.89)], hide_pin_numbers=True))

_add(Sym("FUSE", "F",
         [rect(-5.08, -2.54, 5.08, 2.54)],
         [Pin(1, "~", -10.16, 0, 0, "passive", 5.08),
          Pin(2, "~", 10.16, 0, 180, "passive", 5.08)], hide_pin_numbers=True))


# --------------------------------------------------------------------------- #
# sheet content model
# --------------------------------------------------------------------------- #
class Sheet:
    def __init__(self):
        self.instances = []   # (Sym, ref, value, x, y, ref_off, ref_j, val_off, val_j)
        self.wires = []
        self.labels = []
        self.junctions = []
        self.no_connects = []
        self.texts = []
        self.rects = []

    def place(self, lib, ref, value, x, y,
              ref_off=(0, -11.43), ref_j="center",
              val_off=(0, 11.43), val_j="center"):
        inst = (SYMS[lib], ref, value, x, y, ref_off, ref_j, val_off, val_j)
        self.instances.append(inst)
        return inst

    def pin(self, inst, number):
        """Screen position of a pin on a placed instance."""
        sym, _ref, _value, ox, oy = inst[:5]
        p = sym.pin(number)
        return (round(ox + p.ox, 4), round(oy + p.oy, 4))

    def wire(self, a, b):
        assert a != b, f"zero-length wire at {a}"
        self.wires.append((a, b))

    def stub(self, inst, number, direction, length, text, justify=None):
        """Wire from a pin out to a net label; returns the label anchor."""
        px, py = self.pin(inst, number)
        d = {"L": (-1, 0), "R": (1, 0), "U": (0, -1), "D": (0, 1)}[direction]
        end = (round(px + d[0] * length, 4), round(py + d[1] * length, 4))
        self.wire((px, py), end)
        if justify is None:
            justify = {"L": "right bottom", "R": "left bottom",
                       "U": "left bottom", "D": "left top"}[direction]
        self.label(text, end, justify)
        return end

    def label(self, text, pt, justify):
        self.labels.append((text, pt[0], pt[1], justify))

    def zone(self, x1, y1, x2, y2, title):
        self.rects.append((x1, y1, x2, y2))
        self.texts.append((title, x1 + 4, y1 + TXT_ZONE + 2, TXT_ZONE, True))


def build() -> Sheet:
    sh = Sheet()

    # ---------------- sheet furniture ------------------------------------- #
    # Left-aligned with the zone boxes so the heading reads as part of the
    # drawing rather than floating near the frame border.
    sh.texts.append(("GEOFENCE -- AUTONOMOUS SMART LAWN MOWER",
                     CONTENT_LEFT, 25, TXT_TITLE, True))
    sh.texts.append(("Raspberry Pi 5 hardware interconnect  --  differential drive,"
                     " GPS boundary enforcement, ultrasonic obstacle avoidance",
                     CONTENT_LEFT, 34, TXT_SUB, False))

    # Rows are budgeted to fill the sheet.  Note that the whole content column
    # (CONTENT_LEFT..CONTENT_RIGHT) sits left of the worksheet title block
    # (x 473.5+), so the lower rows are free to run down to the frame.
    sh.zone(CONTENT_LEFT, 42, 196, 200, "RASPBERRY PI 5 -- GPIO HEADER (J8)")
    sh.zone(202, 42, 320, 200, "GPS RECEIVER (UART)")
    sh.zone(326, 42, CONTENT_RIGHT, 200, "BOUNDARY INDICATORS")
    sh.zone(CONTENT_LEFT, 208, CONTENT_RIGHT, 306,
            "DIFFERENTIAL DRIVE -- BTS7960 + DRIVE MOTORS")
    sh.zone(CONTENT_LEFT, 314, 300, 404,
            "OBSTACLE SENSOR -- HC-SR04 + 3.3V LEVEL SHIFT")
    sh.zone(306, 314, CONTENT_RIGHT, 404,
            "MOTOR SUPPLY -- EXTERNAL BATTERY")

    # ---------------- zone A: Raspberry Pi header -------------------------- #
    J1 = sh.place("RPI5_J8_HEADER", "J1", "Raspberry Pi 5 (J8 40-pin GPIO)",
                  106.68, 129.54,
                  ref_off=(0, -69.54), ref_j="center",
                  val_off=(0, -61.54), val_j="center")

    # net attached to every pin that is actually used; None -> no-connect flag
    J1_NETS = {
        1: None, 2: "+5V", 3: None, 4: None,
        5: None, 6: "GND", 7: None, 8: "GPIO14_TXD",
        9: "GND", 10: "GPIO15_RXD", 11: "GPIO17_BUZZER", 12: "GPIO18_R_RPWM",
        13: "GPIO27_LED_RED", 14: "GND", 15: "GPIO22_LED_GRN", 16: "GPIO23_TRIG",
        17: None, 18: "GPIO24_ECHO", 19: None, 20: "GND",
        21: None, 22: None, 23: None, 24: None,
        25: "GND", 26: None, 27: None, 28: None,
        29: None, 30: "GND", 31: None, 32: "GPIO12_L_RPWM",
        33: "GPIO13_L_LPWM", 34: "GND", 35: "GPIO19_R_LPWM", 36: "GPIO16_R_REN",
        37: "GPIO26_R_LEN", 38: "GPIO20_L_REN", 39: "GND", 40: "GPIO21_L_LEN",
    }
    for number, net in J1_NETS.items():
        px, py = sh.pin(J1, number)
        if net is None:
            sh.no_connects.append((px, py))
        else:
            sh.stub(J1, number, "L" if number % 2 else "R", 5.08, net)

    # ---------------- zone B: GPS + local decoupling ----------------------- #
    U1 = sh.place("NEO_M8N_GPS", "U1", "NEO-M8N GPS", 260.35, 88.9,
                  ref_off=(0, -30.48), ref_j="center",
                  val_off=(0, -22.86), val_j="center")
    sh.stub(U1, 1, "L", 5.08, "+5V")
    sh.stub(U1, 2, "L", 5.08, "GND")
    sh.stub(U1, 3, "R", 5.08, "GPIO15_RXD")   # GPS TXD -> Pi RXD (GPIO15)
    sh.stub(U1, 4, "R", 5.08, "GPIO14_TXD")   # Pi TXD (GPIO14) -> GPS RXD

    C1 = sh.place("C", "C1", "100nF", 215.9, 160.02,
                  ref_off=(6.35, -3.81), ref_j="left",
                  val_off=(6.35, 3.81), val_j="left")
    sh.stub(C1, 1, "U", 10.16, "+5V")
    sh.stub(C1, 2, "D", 10.16, "GND")
    sh.texts.append(("C1: local decoupling", 240, 160.02, TXT, False))

    # ---------------- zone C: buzzer + status LEDs ------------------------- #
    BZ1 = sh.place("BUZZER", "BZ1", "Buzzer", 330.2, 100.33,
                   ref_off=(12.7, -3.81), ref_j="left",
                   val_off=(12.7, 3.81), val_j="left")
    sh.stub(BZ1, 1, "U", 12.7, "GPIO17_BUZZER")
    sh.stub(BZ1, 2, "D", 12.7, "GND")

    for x, rref, dref, net, colour in (
            (375.92, "R1", "D1", "GPIO27_LED_RED", "LED_Red"),
            (419.1, "R2", "D2", "GPIO22_LED_GRN", "LED_Green")):
        r = sh.place("R", rref, "220R", x, 90.17,
                     ref_off=(5.08, -3.81), ref_j="left",
                     val_off=(5.08, 3.81), val_j="left")
        d = sh.place("LED", dref, colour, x, 113.03,
                     ref_off=(12.7, -3.81), ref_j="left",
                     val_off=(12.7, 3.81), val_j="left")
        sh.stub(r, 1, "U", 12.7, net)
        sh.wire(sh.pin(r, 2), sh.pin(d, 1))
        sh.stub(d, 2, "D", 12.7, "GND")

    # ---------------- zone D: drivers, motors, local decoupling ------------ #
    U_L = sh.place("BTS7960", "U_L", "BTS7960 (L motor)", 100.33, 254,
                   ref_off=(0, -29.21), ref_j="center",
                   val_off=(0, 31.75), val_j="center")
    U_R = sh.place("BTS7960", "U_R", "BTS7960 (R motor)", 247.65, 254,
                   ref_off=(0, -29.21), ref_j="center",
                   val_off=(0, 31.75), val_j="center")

    for u, mref, mval, rpwm, lpwm, ren, len_ in (
            (U_L, "M_L", "L Drive Motor", "GPIO12_L_RPWM", "GPIO13_L_LPWM",
             "GPIO20_L_REN", "GPIO21_L_LEN"),
            (U_R, "M_R", "R Drive Motor", "GPIO18_R_RPWM", "GPIO19_R_LPWM",
             "GPIO16_R_REN", "GPIO26_R_LEN")):
        sh.stub(u, 1, "L", 7.62, "+5V")
        sh.stub(u, 2, "L", 7.62, "GND")
        sh.stub(u, 3, "L", 7.62, rpwm)
        sh.stub(u, 4, "L", 7.62, lpwm)
        sh.stub(u, 5, "L", 7.62, ren)
        sh.stub(u, 6, "L", 7.62, len_)
        # current-sense outputs are unused on this build
        sh.no_connects.append(sh.pin(u, 7))
        sh.no_connects.append(sh.pin(u, 8))
        sh.stub(u, 9, "R", 7.62, "+VMOTOR")
        sh.stub(u, 10, "R", 7.62, "GND")

        # The motor's two pins are 10.16 mm apart, exactly like the driver's
        # M+/M-.  Centre the motor on that pair so both links are straight
        # horizontal wires rather than diagonals.  The offset right is well
        # clear of the driver's right-hand pin field, and the ref/value go
        # below the circle because above it is where the driver's B+/B- net
        # labels sit.
        m = sh.place("DC_MOTOR", mref, mval, u[3] + 52.07, 261.62,
                     ref_off=(0, 17.78), ref_j="center",
                     val_off=(0, 27.94), val_j="center")
        sh.wire(sh.pin(u, 11), sh.pin(m, 1))
        sh.wire(sh.pin(u, 12), sh.pin(m, 2))

    for cref, cx in (("C3", 340.36), ("C4", 381.0)):
        c = sh.place("C", cref, "100nF", cx, 236.22,
                     ref_off=(6.35, -3.81), ref_j="left",
                     val_off=(6.35, 3.81), val_j="left")
        sh.stub(c, 1, "U", 10.16, "+5V")
        sh.stub(c, 2, "D", 10.16, "GND")

    # ---------------- zone E: HC-SR04 + level shifter ---------------------- #
    U2 = sh.place("HC_SR04", "U2", "HC-SR04 (Front)", 107.95, 350.52,
                  ref_off=(0, -24.13), ref_j="center",
                  val_off=(0, -16.51), val_j="center")
    sh.stub(U2, 1, "L", 5.08, "+5V")
    sh.stub(U2, 2, "L", 5.08, "GND")
    sh.stub(U2, 3, "R", 5.08, "GPIO23_TRIG")

    # ECHO (5 V) -> R3 1k -> node -> {GPIO24_ECHO, R4 2k -> GND}
    # The node sits at 5 V * 2k/(1k+2k) = 3.33 V, safe for a Pi 5 GPIO.
    # R3's top pin is placed level with ECHO so the link is one orthogonal
    # horizontal wire, not a diagonal.
    e = sh.pin(U2, 4)
    # Ref/value go to the *left* of R3/R4: the right-hand side is where the
    # GPIO24_ECHO label sits, and at this text size the two would touch.
    r3 = sh.place("R", "R3", "1k", 200.66, 363.22,
                  ref_off=(-5.08, -3.81), ref_j="right",
                  val_off=(-5.08, 3.81), val_j="right")
    r4 = sh.place("R", "R4", "2k", 200.66, 383.54,
                  ref_off=(-5.08, -3.81), ref_j="right",
                  val_off=(-5.08, 3.81), val_j="right")
    node = sh.pin(r3, 2)
    sh.wire(e, sh.pin(r3, 1))
    sh.junctions.append(node)
    sh.stub(r3, 2, "R", 15.24, "GPIO24_ECHO")
    sh.wire(node, sh.pin(r4, 1))
    sh.stub(r4, 2, "D", 5.08, "GND")
    sh.texts.append(("R3/R4 divider: 5V x 2k/(1k+2k) = 3.33V (matches WIRING.md)",
                     30, 372, TXT, False))

    C2 = sh.place("C", "C2", "100nF", 255.27, 350.52,
                  ref_off=(6.35, -3.81), ref_j="left",
                  val_off=(6.35, 3.81), val_j="left")
    sh.stub(C2, 1, "U", 10.16, "+5V")
    sh.stub(C2, 2, "D", 10.16, "GND")

    # ---------------- zone F: fused battery rail --------------------------- #
    # B+ -> F1 -> +VMOTOR (feeds both drivers).  The label must be on the far
    # side of the fuse, never bridging it.
    BT1 = sh.place("BATTERY_PACK", "BT1", "External 12-24V Li-ion Pack",
                   335.28, 368.3,
                   ref_off=(12.7, -6.35), ref_j="left",
                   val_off=(12.7, 6.35), val_j="left")
    # F1 sits directly above the pack, on the same x as its + pin, so the
    # battery-to-fuse link is one vertical wire.
    F1 = sh.place("FUSE", "F1", "10A", 345.44, 340.36,
                  ref_off=(0, -7.62), ref_j="center",
                  val_off=(0, 8.89), val_j="center")
    sh.wire(sh.pin(BT1, 1), sh.pin(F1, 1))
    sh.stub(F1, 2, "R", 10.16, "+VMOTOR")
    sh.stub(BT1, 2, "D", 10.16, "GND")

    sh.texts.append(("Battery NEGATIVE ties to the common Pi GND.", 30, 380, TXT, False))
    sh.texts.append(("Battery POSITIVE feeds both BTS7960", 30, 388, TXT, False))
    sh.texts.append(("drivers through F1 (10A).", 30, 396, TXT, False))

    return sh


# --------------------------------------------------------------------------- #
# emitter
# --------------------------------------------------------------------------- #
def emit_instance(sym, ref, value, x, y, ref_off, ref_j, val_off, val_j) -> str:
    out = [f'(symbol (lib_id "GEO:{sym.name}") (at {xs(x)} {xs(y)} 0) (unit 1)']
    out.append("  (exclude_from_sim no) (in_bom yes) (on_board yes) (dnp no)")
    out.append(f'  (uuid "{uid("inst", ref)}")')
    out.append(f'  (property "Reference" "{ref}" '
               f'(at {xs(x + ref_off[0])} {xs(y + ref_off[1])} 0) '
               f"(effects (font (size {xs(TXT)} {xs(TXT)})) (justify {ref_j})))")
    out.append(f'  (property "Value" "{value}" '
               f'(at {xs(x + val_off[0])} {xs(y + val_off[1])} 0) '
               f"(effects (font (size {xs(TXT)} {xs(TXT)})) (justify {val_j})))")
    out.append(f'  (property "Footprint" "" (at {xs(x)} {xs(y)} 0) '
               f"(effects (font (size {xs(TXT)} {xs(TXT)})) hide))")
    for p in sym.pins:
        out.append(f'  (pin "{p.number}" (uuid "{uid("pin", ref, p.number)}"))')
    out.append("  (instances")
    out.append(f'    (project "{PROJECT}"')
    out.append(f'      (path "/{ROOT_UUID}" (reference "{ref}") (unit 1))')
    out.append("    )")
    out.append("  )")
    out.append(")")
    return "\n".join(out)


def emit(sh: Sheet) -> str:
    L = []
    L.append("(kicad_sch")
    L.append("  (version 20231120)")
    L.append('  (generator "eeschema")')
    L.append('  (generator_version "8.0")')
    L.append(f'  (uuid "{ROOT_UUID}")')
    L.append(f'  (paper "{PAGE}")')
    L.append("  (title_block")
    # Keep every field inside the ~103 mm title-block text column: an earlier
    # revision overflowed its frame with a 62-character title.
    L.append('    (title "GEOFENCE -- Lawn Mower Hardware")')
    L.append('    (date "2026-09-16")')
    L.append('    (rev "A")')
    L.append('    (company "al-chris/GEOFENCE")')
    L.append('    (comment 1 "Raspberry Pi 5 + BTS7960 drive + HC-SR04 + NEO-M8N GPS")')
    L.append('    (comment 2 "Wiring, pin map and build steps: see WIRING.md")')
    L.append('    (comment 3 "Text sized for A4 (50 percent) print: 3.0mm source")')
    L.append("  )")
    L.append("  (lib_symbols")
    for name in SYMS:
        L.append("    " + SYMS[name].emit().replace("\n", "\n    "))
    L.append("  )")

    for text, x, y, size, bold in sh.texts:
        bold_s = " bold" if bold else ""
        L.append(f'(text "{text}" (at {xs(x)} {xs(y)} 0) '
                 f"(effects (font (size {xs(size)} {xs(size)}){bold_s}) "
                 f'(justify left)) (uuid "{uid("text", text)}"))')
    for x1, y1, x2, y2 in sh.rects:
        L.append(f"(rectangle (start {xs(x1)} {xs(y1)}) (end {xs(x2)} {xs(y2)}) "
                 f"(stroke (width 0.381) (type default)) (fill (type none)) "
                 f'(uuid "{uid("rect", str(x1), str(y1))}"))')

    for inst in sh.instances:
        L.append(emit_instance(*inst))

    for (ax, ay), (bx, by) in sh.wires:
        L.append(f"(wire (pts (xy {xs(ax)} {xs(ay)}) (xy {xs(bx)} {xs(by)})) "
                 f'(stroke (width 0) (type default)) '
                 f'(uuid "{uid("wire", str((ax, ay)), str((bx, by)))}"))')
    for x, y in sh.junctions:
        L.append(f"(junction (at {xs(x)} {xs(y)}) (diameter 0) (color 0 0 0 0) "
                 f'(uuid "{uid("junction", str((x, y)))}"))')
    for x, y in sh.no_connects:
        L.append(f'(no_connect (at {xs(x)} {xs(y)}) '
                 f'(uuid "{uid("nc", str((x, y)))}"))')
    for text, x, y, justify in sh.labels:
        L.append(f'(label "{text}" (at {xs(x)} {xs(y)} 0) '
                 f"(effects (font (size {xs(TXT)} {xs(TXT)})) (justify {justify})) "
                 f'(uuid "{uid("label", text, str((x, y)))}"))')

    L.append("  (sheet_instances")
    L.append('    (path "/" (page "1"))')
    L.append("  )")
    L.append("  (embedded_fonts no)")
    L.append(")")
    return "\n".join(L) + "\n"


def main():
    content = emit(build())
    with open(OUT, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(content)
    print(f"wrote {OUT}: {len(content)} bytes, {content.count(chr(10))} lines")


if __name__ == "__main__":
    main()
