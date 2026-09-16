# Hardware Wiring Guide — Full System Integration
### Autonomous Smart Lawn Mower (Raspberry Pi 5)

This guide documents the complete hardware wiring for:
- **BTS7960 (IBT-2)** Dual Half-Bridge Motor Drivers (Differential Drive)
- **HC-SR04** Ultrasonic Distance Sensor(s) (Front Obstacle Detection)
- **NEO-M8N** GPS Module (UART)
- **Active Buzzer** & **Status LEDs** (Geofence Indicators)

---

## 1. Master Pin Allocation Table (Raspberry Pi 5 40-Pin Header)

All components are mapped to ensure **zero GPIO conflicts**:

| Pi Physical Pin | BCM GPIO | Component | Function / Pin Label | Direction | Notes |
|:---:|:---:|:---|:---|:---:|:---|
| **Pin 2** | 5V | NEO-M8N & BTS7960 & HC-SR04 | VCC | Power | Logic power supply (5V) |
| **Pin 6** | GND | Common Ground | GND | Power | Shared system ground |
| **Pin 8** | GPIO 14 | NEO-M8N GPS | RX (optional config) | Output | Pi TXD → GPS RX |
| **Pin 10** | GPIO 15 | NEO-M8N GPS | TX (data output) | Input | GPS TXD → Pi RXD |
| **Pin 11** | GPIO 17 | Active Buzzer | Positive (+) | Output | Boundary breach alarm |
| **Pin 13** | GPIO 27 | Red LED | Anode (+) via 220Ω | Output | Outside boundary indicator |
| **Pin 15** | GPIO 22 | Green LED | Anode (+) via 220Ω | Output | Inside boundary indicator |
| **Pin 16** | GPIO 23 | Front HC-SR04 | TRIG | Output | 10µs ultrasonic trigger |
| **Pin 18** | GPIO 24 | Front HC-SR04 | ECHO | Input | **Must use voltage divider!** |
| **Pin 32** | GPIO 12 | Left Motor (BTS7960) | RPWM | Output | Left forward speed PWM |
| **Pin 33** | GPIO 13 | Left Motor (BTS7960) | LPWM | Output | Left reverse speed PWM |
| **Pin 38** | GPIO 20 | Left Motor (BTS7960) | R_EN | Output | Left right-enable |
| **Pin 40** | GPIO 21 | Left Motor (BTS7960) | L_EN | Output | Left left-enable |
| **Pin 12** | GPIO 18 | Right Motor (BTS7960) | RPWM | Output | Right forward speed PWM |
| **Pin 35** | GPIO 19 | Right Motor (BTS7960) | LPWM | Output | Right reverse speed PWM |
| **Pin 36** | GPIO 16 | Right Motor (BTS7960) | R_EN | Output | Right right-enable |
| **Pin 37** | GPIO 26 | Right Motor (BTS7960) | L_EN | Output | Right left-enable |

---

## 2. BTS7960 Motor Driver Wiring

Each BTS7960 module controls one high-power DC motor:

```
Raspberry Pi 5                                BTS7960 Driver
GPIO 12 (Pin 32) ───────────────────────────> RPWM (Forward PWM)
GPIO 13 (Pin 33) ───────────────────────────> LPWM (Reverse PWM)
GPIO 20 (Pin 38) ───────────────────────────> R_EN (Forward Enable)
GPIO 21 (Pin 40) ───────────────────────────> L_EN (Reverse Enable)
5V (Pin 2 or 4) ────────────────────────────> VCC (Logic Power)
GND (Pin 6, 9, 14, 20, 25, 30, 34, or 39) ──> GND (Logic Ground)

External Battery (+) ───────────────────────> B+ / Power Screw Terminal (+)
External Battery (-) ───────────────────────> B- / Power Screw Terminal (-)
Motor Leads          ───────────────────────> M+ / M- (Motor Terminals)
```

> [!CAUTION]
> **Never power motors from the Raspberry Pi 5V header.** Always use an external battery (e.g. 12V / 24V lithium pack) connected directly to the BTS7960 screw terminals, with battery negative tied to the Pi's common GND.

---

## 3. HC-SR04 Ultrasonic Sensor Wiring (Voltage Divider)

HC-SR04 runs on **5V logic**, but Raspberry Pi 5 GPIO pins are **3.3V-only inputs**. A resistive voltage divider must be placed on the `ECHO` output:

```
HC-SR04                                                Raspberry Pi 5
VCC    ●───────────────────────────────────────────────● 5V (Pin 2 or 4)
TRIG   ●───────────────────────────────────────────────● GPIO 23 (Pin 16)
ECHO   ●──────┬─────────[ 1 kΩ ]─────────┬─────────────● GPIO 24 (Pin 18)
              │                          │
            (5V)                      [ 2 kΩ ]
                                         │
GND    ●─────────────────────────────────┴─────────────● GND (Pin 6)
```

* Voltage equation: $V_{out} = 5\text{V} \times \frac{2\text{k}\Omega}{1\text{k}\Omega + 2\text{k}\Omega} \approx 3.33\text{V}$ (Safe for Pi 5).

---

## 4. GPS, Buzzer, and LED Wiring

| Component | Pin | Pi Pin | BCM GPIO | Notes |
|:---|:---|:---|:---|:---|
| **NEO-M8N GPS** | VCC | Pin 2/4 | 5V | Power |
| | GND | Pin 6 | GND | Common Ground |
| | TX | Pin 10 | GPIO 15 | GPS UART output to Pi RXD |
| | RX | Pin 8 | GPIO 14 | GPS UART input from Pi TXD |
| **Active Buzzer** | Positive (+) | Pin 11 | GPIO 17 | High = Sound alarm |
| | Negative (−) | Pin 9 | GND | Ground |
| **Red LED** | Anode (+) | Pin 13 | GPIO 27 | In series with 220Ω resistor |
| | Cathode (−) | Pin 14 | GND | Ground |
| **Green LED** | Anode (+) | Pin 15 | GPIO 22 | In series with 220Ω resistor |
| | Cathode (−) | Pin 20 | GND | Ground |

---

## 5. Testing & Operation

### Step 1: Safe Sensor Verification (Motors Disconnected)
With the motor battery pack disconnected:
```bash
python3 scripts/motor_ultrasonic_control.py --mode status
```
Wave your hand in front of the sensor to verify readings.

### Step 2: Motor Ramp Sweep (Wheels on Blocks)
Elevate the robot so the wheels spin freely, connect battery:
```bash
python3 scripts/motor_ultrasonic_control.py --mode ramp
```

### Step 3: Obstacle Avoidance Demo
```bash
python3 scripts/motor_ultrasonic_control.py --mode obstacle --speed 40 --stop-cm 25
```

### Step 4: Full Integrated Launch (ROS 2)
```bash
source source_all.bash
ros2 launch virtual_geofence geofence_launch.py
```
This starts:
1. NEO-M8N GPS driver (`nmea_serial_driver`)
2. `geofence_node` (boundary monitor, buzzer, LEDs, stop publisher)
3. `motor_controller_node` (BTS7960 motor driver, HC-SR04 publisher, obstacle auto-stop)
