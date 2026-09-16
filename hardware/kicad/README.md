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
on: unbalanced parentheses, dangling wire ends, pins that are neither wired nor
no-connected, stray no-connect flags, off-grid connection points, symbol
bounding-box overlaps, text overlaps, content overlapping the worksheet title
block or falling outside the drawing frame, and any deviation from the
reference netlist that it extracts and prints.

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

The A2 worksheet's title block occupies x 484–592, y 386–418 mm — keep content
out of that corner.
