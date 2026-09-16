# GEOFENCE — KiCad Hardware Schematic

`geofence_lawnmower.kicad_sch` is the full hardware interconnect for the
autonomous lawn mower described in [`../../WIRING.md`](../../WIRING.md) and
[`../../setup.md`](../../setup.md):

- Raspberry Pi 5 J8 (40-pin) GPIO header, every pin labelled with its BCM
  function
- NEO-M8N GPS module (UART0, `/dev/ttyAMA0`)
- 2x BTS7960 half-bridge drivers for differential drive, each feeding a
  drive motor, plus a fused external 12–24V battery rail (`+VMOTOR`) that is
  kept completely isolated from the Pi's own 5V rail
- HC-SR04 front ultrasonic sensor with the 1kΩ/2kΩ ECHO voltage divider
  (5V × 2k/3k ≈ 3.33V) required to protect the Pi 5's 3.3V-only GPIO inputs
- Active buzzer + red/green boundary-status LEDs
- 100nF local decoupling capacitors on every module's supply pins and a
  10A fuse on the motor battery line (both are sensible additions on top of
  what WIRING.md documents — they don't change any pin mapping)

All nets are connected via matching net labels (e.g. every wire tagged
`GPIO12_L_RPWM` is the same electrical net) rather than long routed wires,
which keeps the sheet readable given how many signals fan out from the
40-pin header.

## Viewing / verifying

No local KiCad install was available when this was authored, so the file
was hand-built and verified directly against
**[kicanvas.org](https://kicanvas.org)**:

```
https://kicanvas.org/?github=<URL to this file on GitHub>
```

or simply drag-and-drop `geofence_lawnmower.kicad_sch` onto
<https://kicanvas.org>. Every wire endpoint was confirmed (programmatically,
via kicanvas's own parsed schematic data) to terminate on a real pin,
label, junction, or no-connect flag — i.e. there are no dangling nets.

Open `geofence_lawnmower.kicad_pro` in KiCad 8/9 to edit natively.
