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

  (equivalently, KiCad's placement transform is ``[1,0,0,-1]``).  This is
  verified empirically against the KiCad demo projects: over six demos, 48
  pin/wire coincidences only fit the negated-Y rule versus 1 that only fits the
  naive ``+local_y`` rule.

  So :func:`Sym.emit` negates every library pin/graphic Y (and negates pin
  angles), after which a pin's on-sheet position is simply

      instance_origin + pin.offset

  and no caller ever has to think about the flip again.

Run ``python verify_schematic.py`` after regenerating: it re-derives every pin
position *from the emitted file* using that same transform and fails loudly on
dangling wires, unconnected pins, off-grid endpoints or overlapping symbols.
"""

from __future__ import annotations

import uuid

OUT = "geofence_lawnmower.kicad_sch"
PROJECT = "geofence_lawnmower"
ROOT_UUID = "9ed750d8-e90f-4cb6-aa14-8059ae2348b4"

GRID = 1.27  # 50 mil


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
    ``angle`` is the SCREEN direction the pin extends in, i.e. the direction
    from the connection point towards the symbol body:

        0 = +X (pin on the left  side of a body)
      180 = -X (pin on the right side of a body)
       90 = +Y (pin on the top     of a body, body below it)
      270 = -Y (pin on the bottom  of a body, body above it)
    """

    __slots__ = ("number", "name", "ox", "oy", "angle", "etype", "length")

    def __init__(self, number, name, ox, oy, angle, etype="passive", length=2.54):
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
            f'  (name "{self.name}" (effects (font (size 1.27 1.27))))\n'
            f'  (number "{self.number}" (effects (font (size 1.27 1.27))))\n'
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
            f"(effects (font (size 1.27 1.27)) hide))\n"
            + f'  (property "Value" "{self.name}" (at 0 0 0) '
            f"(effects (font (size 1.27 1.27)) hide))\n"
            + f'  (property "Footprint" "" (at 0 0 0) '
            f"(effects (font (size 1.27 1.27)) hide))\n"
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
# --------------------------------------------------------------------------- #
# 40-pin Raspberry Pi header.  Pin 1 top-left, pin 2 top-right (the real J8
# layout), odd pins on the left, even on the right.
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

HEADER_W2 = 20.32          # half body width
HEADER_H2 = 25.4           # half body height
HEADER_ROW0 = -24.13       # screen offset of row 0 (pin 1 / pin 2)


def _header_pins():
    pins = []
    for k, (number, name) in enumerate(HEADER_ROWS):
        oy = HEADER_ROW0 + (k // 2) * 2.54
        left = number % 2 == 1
        etype = "power_out" if name in ("3V3", "5V") else (
            "passive" if name == "GND" else "bidirectional")
        pins.append(Pin(number, name, -HEADER_W2 - 2.54 if left else HEADER_W2 + 2.54,
                        oy, 0 if left else 180, etype))
    return pins


SYMS = {}


def _add(sym):
    SYMS[sym.name] = sym


_add(Sym("RPI5_J8_HEADER", "J",
         [rect(-HEADER_W2, -HEADER_H2, HEADER_W2, HEADER_H2)],
         _header_pins()))

_add(Sym("NEO_M8N_GPS", "U",
         [rect(-12.7, -7.62, 12.7, 7.62)],
         [Pin(1, "VCC", -15.24, -5.08, 0, "power_in"),
          Pin(2, "GND", -15.24, 5.08, 0, "passive"),
          Pin(3, "TXD", 15.24, -5.08, 180, "output"),
          Pin(4, "RXD", 15.24, 5.08, 180, "input")]))

_add(Sym("HC_SR04", "U",
         [rect(-12.7, -7.62, 12.7, 7.62)],
         [Pin(1, "VCC", -15.24, -5.08, 0, "power_in"),
          Pin(2, "GND", -15.24, 5.08, 0, "passive"),
          Pin(3, "TRIG", 15.24, -5.08, 180, "input"),
          Pin(4, "ECHO", 15.24, 5.08, 180, "output")]))

_add(Sym("BTS7960", "U",
         [rect(-15.24, -11.43, 15.24, 11.43)],
         [Pin(1, "VCC", -17.78, -8.89, 0, "power_in"),
          Pin(2, "GND", -17.78, -6.35, 0, "passive"),
          Pin(3, "RPWM", -17.78, -3.81, 0, "input"),
          Pin(4, "LPWM", -17.78, -1.27, 0, "input"),
          Pin(5, "R_EN", -17.78, 1.27, 0, "input"),
          Pin(6, "L_EN", -17.78, 3.81, 0, "input"),
          Pin(7, "R_IS", -17.78, 6.35, 0, "output"),
          Pin(8, "L_IS", -17.78, 8.89, 0, "output"),
          Pin(9, "B+", 17.78, -8.89, 180, "power_in"),
          Pin(10, "B-", 17.78, -3.81, 180, "power_in"),
          Pin(11, "M+", 17.78, 1.27, 180, "output"),
          Pin(12, "M-", 17.78, 6.35, 180, "output")]))

# Resistor: pin 1 on top, pin 2 on the bottom (the KiCad convention).
_add(Sym("R", "R",
         [rect(-1.27, -2.54, 1.27, 2.54)],
         [Pin(1, "~", 0, -3.81, 90, "passive", 1.27),
          Pin(2, "~", 0, 3.81, 270, "passive", 1.27)], hide_pin_numbers=True))

_add(Sym("C", "C",
         [poly([(-1.905, -0.635), (1.905, -0.635)], 0.508),
          poly([(-1.905, 0.635), (1.905, 0.635)], 0.508)],
         [Pin(1, "~", 0, -3.81, 90, "passive", 3.175),
          Pin(2, "~", 0, 3.81, 270, "passive", 3.175)], hide_pin_numbers=True))

# LED drawn pointing DOWN: anode (pin 1) on top, cathode (pin 2) below.
_add(Sym("LED", "D",
         [poly([(-1.27, -1.27), (1.27, -1.27), (0, 1.27), (-1.27, -1.27)]),
          poly([(-1.27, 1.27), (1.27, 1.27)], 0.381),
          poly([(1.905, -0.508), (3.302, -1.905)]),
          poly([(3.302, -1.905), (2.286, -1.778)]),
          poly([(3.302, -1.905), (3.175, -0.889)]),
          poly([(2.413, 0.762), (3.81, -0.635)]),
          poly([(3.81, -0.635), (2.794, -0.508)]),
          poly([(3.81, -0.635), (3.683, 0.381)])],
         [Pin(1, "A", 0, -3.81, 90, "passive"),
          Pin(2, "K", 0, 3.81, 270, "passive")], hide_pin_numbers=True))

_add(Sym("BUZZER", "BZ",
         [circle(0, 0, 3.175)],
         [Pin(1, "+", 0, -3.81, 90, "passive"),
          Pin(2, "-", 0, 3.81, 270, "passive")], hide_pin_numbers=True))

_add(Sym("DC_MOTOR", "M",
         [circle(0, 0, 6.35, 0.381)],
         [Pin(1, "+", -8.89, -2.54, 0, "passive", 3.81),
          Pin(2, "-", -8.89, 2.54, 0, "passive", 3.81)], hide_pin_numbers=True))

_add(Sym("BATTERY_PACK", "BT",
         [poly([(-4.445, -6.35), (4.445, -6.35)], 0.762),
          poly([(-2.286, -4.445), (2.286, -4.445)], 0.381),
          poly([(-4.445, -1.905), (4.445, -1.905)], 0.762),
          poly([(-2.286, 0.0), (2.286, 0.0)], 0.381),
          poly([(-4.445, 2.54), (4.445, 2.54)], 0.762),
          poly([(-2.286, 4.445), (2.286, 4.445)], 0.381)],
         # The pack is the source of the +VMOTOR rail, so its positive terminal
         # is a power_out - that is what stops ERC from reporting the BTS7960
         # B+ power_in pins as undriven.
         [Pin(1, "+", 0, -8.89, 90, "power_out", 2.54),
          Pin(2, "-", 0, 8.89, 270, "passive", 4.445)], hide_pin_numbers=True))

_add(Sym("FUSE", "F",
         [rect(-2.54, -1.27, 2.54, 1.27)],
         [Pin(1, "~", -5.08, 0, 0, "passive"),
          Pin(2, "~", 5.08, 0, 180, "passive")], hide_pin_numbers=True))


# --------------------------------------------------------------------------- #
# sheet content model
# --------------------------------------------------------------------------- #
class Sheet:
    def __init__(self):
        self.instances = []   # (Sym, ref, value, x, y, ref_off, ref_j, val_off, val_j)
        self.wires = []       # ((x1,y1),(x2,y2))
        self.labels = []      # (text, x, y, justify)
        self.junctions = []   # (x, y)
        self.no_connects = [] # (x, y)
        self.texts = []       # (text, x, y, size, bold)
        self.rects = []       # (x1,y1,x2,y2)

    def place(self, lib, ref, value, x, y,
              ref_off=(-3.302, -1.27), ref_j="right",
              val_off=(-3.302, 1.27), val_j="right"):
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


def build() -> Sheet:
    sh = Sheet()

    # ---------------- sheet furniture ------------------------------------- #
    # The KiCad A2 worksheet title block occupies x 484..592, y 386..418, so
    # every zone is kept clear of that corner.
    sh.texts.append(("GEOFENCE -- AUTONOMOUS SMART LAWN MOWER", 20, 14, 2.6, True))
    sh.texts.append(("Raspberry Pi 5 Hardware Interconnect  --  Differential Drive,"
                     " GPS Boundary Enforcement, Ultrasonic Obstacle Avoidance",
                     20, 19, 1.3, False))

    sh.rects.append((18, 30, 200, 134))
    sh.texts.append(("RASPBERRY PI 5 -- GPIO HEADER (J8)", 20, 36, 3, True))
    sh.rects.append((210, 30, 440, 134))
    sh.texts.append(("GPS RECEIVER (UART)  &  BOUNDARY INDICATORS", 212, 36, 3, True))
    sh.rects.append((210, 140, 440, 252))
    sh.texts.append(("OBSTACLE SENSOR -- HC-SR04 + 3.3V LEVEL-SHIFT DIVIDER",
                     212, 146, 3, True))
    sh.rects.append((18, 262, 480, 382))
    sh.texts.append(("DIFFERENTIAL DRIVE -- MOTOR SYSTEM (EXTERNAL BATTERY)",
                     20, 268, 3, True))

    # ---------------- zone A: Raspberry Pi header -------------------------- #
    J1 = sh.place("RPI5_J8_HEADER", "J1", "Raspberry Pi 5 (J8 40-pin GPIO)",
                  106.68, 85.09,
                  ref_off=(0, -31.75), ref_j="center",
                  val_off=(0, -26.67), val_j="center")

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
            sh.stub(J1, number, "L" if number % 2 else "R", 15.24, net)

    # ---------------- zone B: GPS + indicators ----------------------------- #
    U1 = sh.place("NEO_M8N_GPS", "U1", "NEO-M8N GPS", 269.24, 55.88,
                  ref_off=(0, -13.97), ref_j="center",
                  val_off=(0, -9.525), val_j="center")
    sh.stub(U1, 1, "L", 12.7, "+5V")
    sh.stub(U1, 2, "L", 12.7, "GND")
    sh.stub(U1, 3, "R", 12.7, "GPIO15_RXD")   # GPS TXD -> Pi RXD (GPIO15)
    sh.stub(U1, 4, "R", 12.7, "GPIO14_TXD")   # Pi TXD (GPIO14) -> GPS RXD

    C1 = sh.place("C", "C1", "100nF", 240.03, 95.25,
                  ref_off=(2.286, -2.54), ref_j="left",
                  val_off=(2.286, 0.0), val_j="left")
    sh.stub(C1, 1, "U", 7.62, "+5V")
    sh.stub(C1, 2, "D", 8.89, "GND")
    sh.texts.append(("C1: local decoupling", 246.38, 98.425, 1.4, False))

    BZ1 = sh.place("BUZZER", "BZ1", "Active Buzzer", 330.2, 60.96,
                   ref_off=(4.445, -13.97), ref_j="center",
                   val_off=(4.445, -9.525), val_j="center")
    sh.stub(BZ1, 1, "U", 12.7, "GPIO17_BUZZER")
    sh.stub(BZ1, 2, "D", 13.97, "GND")

    # Red / green boundary LEDs, each in series with a 220R resistor.
    for x, rref, dref, net, colour in ((378.46, "R1", "D1", "GPIO27_LED_RED", "LED_Red"),
                                       (419.1, "R2", "D2", "GPIO22_LED_GRN", "LED_Green")):
        r = sh.place("R", rref, "220R", x, 55.88,
                     ref_off=(2.286, -2.54), ref_j="left",
                     val_off=(2.286, 0.0), val_j="left")
        d = sh.place("LED", dref, colour, x, 68.58,
                     ref_off=(4.445, -2.54), ref_j="left",
                     val_off=(4.445, 0.0), val_j="left")
        sh.stub(r, 1, "U", 10.16, net)
        sh.wire(sh.pin(r, 2), sh.pin(d, 1))
        sh.stub(d, 2, "D", 11.43, "GND")

    # ---------------- zone C: HC-SR04 + level shifter ---------------------- #
    U2 = sh.place("HC_SR04", "U2", "HC-SR04 (Front)", 269.24, 190.5,
                  ref_off=(0, -13.97), ref_j="center",
                  val_off=(0, -9.525), val_j="center")
    sh.stub(U2, 1, "L", 12.7, "+5V")
    sh.stub(U2, 2, "L", 12.7, "GND")
    sh.stub(U2, 3, "R", 12.7, "GPIO23_TRIG")

    # ECHO (5 V) -> R3 1k -> node -> {GPIO24_ECHO, R4 2k -> GND}
    # The node sits at 5 V * 2k/(1k+2k) = 3.33 V, safe for a Pi 5 GPIO.
    e = sh.pin(U2, 4)
    r3 = sh.place("R", "R3", "1k", 320.04, 199.39,
                  ref_off=(2.286, -1.27), ref_j="left",
                  val_off=(2.286, 1.27), val_j="left")
    r4 = sh.place("R", "R4", "2k", 320.04, 214.63,
                  ref_off=(2.286, -1.27), ref_j="left",
                  val_off=(2.286, 1.27), val_j="left")
    node = sh.pin(r3, 2)
    sh.wire(e, sh.pin(r3, 1))
    sh.junctions.append(node)
    sh.stub(r3, 2, "R", 15.24, "GPIO24_ECHO")
    sh.wire(node, sh.pin(r4, 1))
    sh.stub(r4, 2, "D", 10.16, "GND")

    C2 = sh.place("C", "C2", "100nF", 240.03, 224.79,
                  ref_off=(2.286, -2.54), ref_j="left",
                  val_off=(2.286, 0.0), val_j="left")
    sh.stub(C2, 1, "U", 11.43, "+5V")
    sh.stub(C2, 2, "D", 8.89, "GND")
    sh.texts.append(("R3/R4 divider: 5V x 2k/(1k+2k) = 3.33V (matches WIRING.md)",
                     218.44, 241.3, 1.4, False))

    # ---------------- zone D: motor drive + battery ------------------------ #
    motors = (
        ("U_L", "L motor", 299.72, "GPIO12_L_RPWM", "GPIO13_L_LPWM",
         "GPIO20_L_REN", "GPIO21_L_LEN", "M_L", "L Drive Motor",
         "C3", 300.99),
        ("U_R", "R motor", 355.6, "GPIO18_R_RPWM", "GPIO19_R_LPWM",
         "GPIO16_R_REN", "GPIO26_R_LEN", "M_R", "R Drive Motor",
         "C4", 356.87),
    )
    for (uref, ulabel, uy, rpwm, lpwm, ren, len_, mref, mval, cref, cy) in motors:
        u = sh.place("BTS7960", uref, f"BTS7960 ({ulabel})", 85.09, uy,
                     ref_off=(0, -13.97), ref_j="center",
                     val_off=(0, 16.51), val_j="center")
        sh.stub(u, 1, "L", 15.24, "+5V")
        sh.stub(u, 2, "L", 15.24, "GND")
        sh.stub(u, 3, "L", 15.24, rpwm)
        sh.stub(u, 4, "L", 15.24, lpwm)
        sh.stub(u, 5, "L", 15.24, ren)
        sh.stub(u, 6, "L", 15.24, len_)
        # current-sense outputs are unused on this build
        sh.no_connects.append(sh.pin(u, 7))
        sh.no_connects.append(sh.pin(u, 8))
        sh.stub(u, 9, "R", 15.24, "+VMOTOR")
        sh.stub(u, 10, "R", 15.24, "GND")

        m = sh.place("DC_MOTOR", mref, mval, 149.86, cy + 2.54,
                     ref_off=(0, -10.16), ref_j="center",
                     val_off=(0, 10.16), val_j="center")
        sh.wire(sh.pin(u, 11), sh.pin(m, 1))
        sh.wire(sh.pin(u, 12), sh.pin(m, 2))

        c = sh.place("C", cref, "100nF", 205.74, cy,
                     ref_off=(2.286, -2.54), ref_j="left",
                     val_off=(2.286, 0.0), val_j="left")
        sh.stub(c, 1, "U", 7.62, "+5V")
        sh.stub(c, 2, "D", 7.62, "GND")

    # Fused battery rail.  B+ -> F1 -> +VMOTOR (feeds both drivers); the
    # label must be on the far side of the fuse, never bridging it.
    BT1 = sh.place("BATTERY_PACK", "BT1", "External 12-24V Li-ion Pack",
                   360.68, 320.04,
                   ref_off=(8.255, -3.81), ref_j="left",
                   val_off=(8.255, 3.81), val_j="left")
    F1 = sh.place("FUSE", "F1", "10A", 365.76, 299.72,
                  ref_off=(0, -4.318), ref_j="center",
                  val_off=(0, 5.08), val_j="center")
    sh.wire(sh.pin(BT1, 1), sh.pin(F1, 1))
    sh.stub(F1, 2, "R", 11.43, "+VMOTOR")
    sh.stub(BT1, 2, "D", 11.43, "GND")

    sh.texts.append(("Battery NEGATIVE ties to the common Pi GND.", 225, 364, 1.6, False))
    sh.texts.append(("Battery POSITIVE feeds BOTH BTS7960 modules through F1.", 225, 370, 1.6, False))
    sh.texts.append(("NEVER power the motors from the Raspberry Pi 5V rail.", 225, 376, 1.6, False))

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
               f"(effects (font (size 1.27 1.27)) (justify {ref_j})))")
    out.append(f'  (property "Value" "{value}" '
               f'(at {xs(x + val_off[0])} {xs(y + val_off[1])} 0) '
               f"(effects (font (size 1.27 1.27)) (justify {val_j})))")
    out.append(f'  (property "Footprint" "" (at {xs(x)} {xs(y)} 0) '
               f"(effects (font (size 1.27 1.27)) hide))")
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
    L.append('  (paper "A2")')
    L.append("  (title_block")
    L.append('    (title "GEOFENCE -- Autonomous Smart Lawn Mower -- Hardware Interconnect")')
    L.append('    (date "2026-09-16")')
    L.append('    (rev "A")')
    L.append('    (company "al-chris/GEOFENCE")')
    L.append('    (comment 1 "Raspberry Pi 5 + BTS7960 differential drive + HC-SR04'
             ' + NEO-M8N GPS + geofence indicators")')
    L.append('    (comment 2 "See WIRING.md and setup.md in the repository for the'
             ' full build guide")')
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
                 f"(effects (font (size 1.27 1.27)) (justify {justify})) "
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
