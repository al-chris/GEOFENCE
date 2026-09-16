# GEOFENCE — KiCad Hardware Schematic

`geofence_lawnmower.kicad_sch` is the full hardware interconnect for the
autonomous lawn mower described in [`../../WIRING.md`](../../WIRING.md) and
[`../../setup.md`](../../setup.md):

- Raspberry Pi 5 J8 (40-pin) GPIO header — pin 1 top-left, odd pins down the
  left column, even pins down the right, exactly as on the physical board.
  Every pin is labelled with its BCM function, and every unused pin carries an
  explicit no-connect flag.
- NEO-M8N GPS module (UART0, `/dev/ttyAMA0`). Note the crossover: GPS `TXD`
  goes to Pi GPIO15 (RXD) and Pi GPIO14 (TXD) goes to GPS `RXD`.
- 2x BTS7960 half-bridge drivers for differential drive, each feeding a drive
  motor. `R_IS`/`L_IS` current-sense outputs are deliberately unconnected.
- A fused external 12–24V battery rail (`+VMOTOR`): battery `+` → `F1` (10A) →
  `+VMOTOR` → both drivers' `B+`. The label sits on the far side of the fuse,
  so the fuse really is in series. Battery `−` ties to the common Pi `GND`; the
  rail is otherwise isolated from the Pi's own 5V rail.
- HC-SR04 front ultrasonic sensor with the 1kΩ/2kΩ ECHO voltage divider:
  `ECHO` → 1kΩ (`R3`) → node → 2kΩ (`R4`) → `GND`, with the node taken to
  GPIO24. The node sits at 5V × 2k/(1k+2k) ≈ 3.33V, which is what protects the
  Pi 5's 3.3V-only GPIO inputs.
- Active buzzer (`GPIO17`) and red/green boundary-status LEDs (`GPIO27`,
  `GPIO22`), each in series with a 220Ω resistor.
- 100nF local decoupling on every module's supply. The decoupling capacitors
  and the fuse are sensible additions on top of WIRING.md — they change no
  documented pin or value.

All nets are connected via matching net labels (e.g. every wire tagged
`GPIO12_L_RPWM` is the same electrical net) rather than long routed wires,
which keeps the sheet readable given how many signals fan out from the
40-pin header.

## Sizing: this sheet is meant to be printed on A4

The sheet is A2, but it is written into reports on A4 — a 50% linear
reduction. Text is therefore set at **3.0 mm** so it lands at ~1.5 mm on paper,
which is slightly *better* than a native A4 KiCad schematic (KiCad's default
text is 1.27 mm).

Symbol bodies and pin pitches are scaled up to match (pin pitch is 5.08 mm),
because a schematic symbol is a drawing convention rather than a physical
dimension — nothing here is drawn to scale, and the header is still drawn with
pin 1 top-left, odd pins down the left column and even pins down the right,
exactly as on the real J8.

If you instead print at 100% on **A2**, the text will simply look large: that
is the trade the drawing is making, and it is deliberate.

## Files

| File | Purpose |
|:--|:--|
| `geofence_lawnmower.kicad_sch` | The schematic. **Generated** — do not hand-edit. |
| `generate_schematic.py` | Declarative generator. Edit this, not the `.kicad_sch`. |
| `verify_schematic.py` | Independent checker + netlist extractor. |
| `check_pin_convention.py` | Confirms the KiCad placement convention (see below). Needs network. |
| `geofence_lawnmower.kicad_pro` | Project file, for opening natively in KiCad 8/9. |

```bash
python generate_schematic.py       # regenerate the .kicad_sch
python verify_schematic.py         # must print "ALL CHECKS PASSED"
python check_pin_convention.py     # must print "negated-Y placement confirmed"
```

`verify_schematic.py` deliberately does **not** import the generator. It
re-parses the emitted file from scratch and re-derives every pin position, so a
generator bug cannot hide behind the same assumption in the checker. It fails
on: unbalanced parentheses, dangling wire ends, diagonal wires (a diagonal link
between two pins always means a real misalignment), pins that are neither wired
nor no-connected, stray no-connect flags, off-grid connection points, symbol
bounding-box overlaps, text overlaps, title-block fields too long for their
column, content overlapping the worksheet title block or falling outside the
drawing frame, and any deviation from the reference netlist that it extracts
and prints.

The diagonal-wire check earns its place: it was added after a layout edit
silently introduced four diagonal driver-to-motor links, which looked
plausible on screen but meant the motor pins were never aligned with the
driver's `M+`/`M-` to begin with.

## Editing this schematic

Everything in `generate_schematic.py` is written in **screen coordinates**
(+X right, +Y **down**, millimetres) — the frame you actually reason in when
laying a schematic out, and the frame used by `wire`, `label`, `junction`,
`no_connect`, `text` and `rectangle` in a `.kicad_sch` file.

Symbol-library geometry is different: KiCad stores it **Y-up** and draws an
unrotated, unmirrored instance with

```
screen = instance_origin + (local_x, -local_y)      # placement transform [1,0,0,-1]
```

So `Sym.emit()` negates every library pin/graphic Y (and every pin angle) on the
way out, after which a pin's on-sheet position is simply
`instance_origin + pin.offset` and no caller has to think about the flip again.

> **Getting this wrong is the classic failure mode for this file.** An earlier
> revision used `+local_y` throughout. That is self-consistent — the generator
> and its own checker agreed, and the wires were laid at exactly the
> coordinates the generator *thought* the pins were at — but KiCad mirrored
> every symbol about its own origin, so **not one wire touched its pin**. The
> sheet looked plausible in a netlist diff and was completely wrong on screen.
>
> So don't take the convention on faith: run `python check_pin_convention.py`.
> It downloads upstream KiCad demos and counts pin/wire coincidences under both
> rules. Real-world result: 48 pins fit only the negated-Y rule, 1 fits only
> the naive rule (a stray wire endpoint on an unconnected `ICL7660` pin, which
> the script reports for judgement), and 68 are vertically symmetric parts
> where both rules predict the same points. Re-run it if you change the
> placement maths — do not just trust `verify_schematic.py`, because a
> generator and a checker sharing a wrong assumption agree perfectly.

## Viewing / verifying without a local KiCad install

`kicanvas.org` is the renderer of record here; that is how the current revision
was verified.

```
https://kicanvas.org/?github=<URL to this file on GitHub>
```

or drag-and-drop `geofence_lawnmower.kicad_sch` onto <https://kicanvas.org>.

KiCad is not installed on the machine this was authored on, so the `.kicad_sch`
has **not** been through `kicad-cli sch erc`. `verify_schematic.py` covers
connectivity, geometry and the netlist, but an ERC run in KiCad is still worth
doing before fabrication.

### Verification performed on this revision

1. **Parsed-model connectivity** — every wire endpoint terminates on a real
   pin, label or junction (0 dangling ends); every pin is either wired or
   flagged no-connect; all connection points are on the 1.27mm grid.
2. **Extracted netlist** — the union-find netlist read back out of the file
   matches the reference table in `verify_schematic.py` terminal-for-terminal,
   including the anonymous nets (LED series resistors, motor terminals, and
   battery `+` → fuse).
3. **Rendered inspection** — every functional zone was inspected at high zoom
   in kicanvas and confirmed to have wires landing on pins, no text or graphic
   overlaps, and nothing under the worksheet title block.

To re-do (3) quickly, kicanvas's camera is reachable from a browser console via
the viewer's shadow DOM:

```js
function findDeep(root, sel) {
  const found = [];
  (function walk(node) {
    if (node.querySelectorAll) for (const el of node.querySelectorAll(sel)) found.push(el);
    for (const c of Array.from(node.children || [])) { if (c.shadowRoot) walk(c.shadowRoot); walk(c); }
  })(root);
  return found;
}
const v = findDeep(document, 'kc-schematic-viewer')[0];
const cam = v.viewer.viewport.camera;      // {center: {x, y}, zoom, ...}
cam.center = { x: 106.68, y: 85.09 };      // frame the header
cam.zoom = v.viewer.viewport.width / 130;  // 130 mm wide
v.viewer.draw();
```

The A2 worksheet's drawing frame inner border sits 10 mm in from each page
edge. KiCad's title block is a fixed 108 × 32 mm rectangle anchored to the
**frame's** bottom-right corner — *not* the page corner, which is an easy and
silent mistake: assuming the page corner put zone D underneath the title block.
On A2 the keep-out is therefore x 473.5–582, y 375.9–408 mm, and the whole
content column (`CONTENT_LEFT`…`CONTENT_RIGHT`, x 18–470) sits clear of it, so
every zone box shares the same left and right edge.

Those numbers were measured off the rendered sheet rather than assumed. The
reliable way to do that is to read the canvas pixels and count red-dominant
pixels per column and per row across the block: a border is continuous, text is
not. Under the light "Witch Hazel" theme the frame lines are muted red blended
toward a near-white background, so test `r > 150 && r-g > 15 && r-b > 15`
rather than a dark-red threshold.

Title-block text overflows its column silently, so the *fields* are kept short
and `verify_schematic.py` checks their length too.
