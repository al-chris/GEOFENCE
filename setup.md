# How to Run virtual_geofence on Ubuntu Server 24.04

This guide covers both the **Real Hardware (Raspberry Pi)** and **Simulation (Laptop/PC)** setups.

---

## Gazebo Troubleshooting & Migration Summary
**Environment:** ROS 2 Jazzy, Gazebo Harmonic, Ubuntu WSL2

### Why WSL2?
Traditional Virtual Machines (VMware/VirtualBox) often suffer from severe 3D rendering issues in Gazebo Harmonic (Ogre2 engine), including unusable lag or violent flickering. WSL2 (via WSLg) provides direct GPU passthrough, allowing near-native performance without the need for hacky software rendering overrides.

---

## Part 1: Flashing Ubuntu Server to the SD Card

> **Warning:** This process will completely erase the existing OS and all data on the SD card. Back up any important files before proceeding.

This section applies if you are starting from a fresh SD card, or migrating from another OS (e.g. Raspberry Pi OS Trixie/Bookworm).

### 1. Download Raspberry Pi Imager

On your main computer (Windows, Mac, or Linux), download the Raspberry Pi Imager from the official website: https://www.raspberrypi.com/software/

### 2. Select the Device and OS

Insert your SD card into your computer's SD card reader and open Raspberry Pi Imager.

- Under **Choose Device**, select **Raspberry Pi 5**.
- Under **Choose OS**, do not select the default Raspberry Pi OS. Instead:
  - Click **Other general-purpose OS**
  - Click **Ubuntu**
  - Select **Ubuntu Server 24.04 LTS (64-bit)** (or the latest LTS version available).

> **Note:** The Raspberry Pi 5 is 64-bit only — Ubuntu Server 24.04 LTS (64-bit) is the correct image.

### 3. Configure Settings

Click **Choose Storage** and select your SD card. Click **Next**.

When prompted about OS customization settings, click **Edit Settings** and configure the following:

- **General tab:** Set a hostname, username, and password. Configure Wi-Fi if you want the Pi to connect to your network automatically on first boot.
- **Services tab:** Enable SSH. This allows you to control the Pi from your main computer, which is especially useful for server installs without a monitor.

Click **Save**, then **Yes** to apply settings.

### 4. Write to the SD Card

Click **Yes** when warned that all existing data will be erased. Wait for the Imager to download, write, and verify the image. Once it says **Write Successful**, remove the SD card.

### 5. First Boot

Insert the SD card into the Raspberry Pi 5 and power it on.

> **Be patient:** The first boot takes several minutes as Ubuntu configures network settings and resizes the filesystem.

Log in using the username and password you set in the Imager.

---

## Part 2: Raspberry Pi 5 — UART Configuration

### The Situation on Pi 5

On the Raspberry Pi 5, the RP1 chip provides several independent PL011 UARTs accessible via different GPIO header pin groups. Unlike the Pi 3, there is **no Bluetooth/UART conflict** on GPIO14/15 — Bluetooth uses a separate UART internally. However, the UART is not enabled on the GPIO header by default; you must load the appropriate device tree overlay.

### Overlay Options

The RP1 chip on Pi 5 exposes the following UARTs across different header pin groups:

| Overlay | TX / RX pins | Device |
|---------|-------------|--------|
| `uart0-pi5` | GPIO14 / GPIO15 (pins 8/10) | `/dev/ttyAMA0` |
| `uart2-pi5` | GPIO4 / GPIO5 (pins 7/29) | `/dev/ttyAMA2` |
| `uart3-pi5` | GPIO8 / GPIO9 (pins 24/21) | `/dev/ttyAMA3` |
| `uart4-pi5` | GPIO12 / GPIO13 (pins 32/33) | `/dev/ttyAMA4` |

> **Note:** There is no `uart1` as a distinct PL011 on Pi 5 the way there was on Pi 3. Pi 5 uses a set of PL011s via the RP1 chip — no mini-UART tradeoff exists.

### Recommended: `uart0-pi5` (matches existing wiring)

Since the GPS module is already wired to GPIO14/15 (physical pins 8/10), load the `uart0-pi5` overlay:

```bash
echo "dtoverlay=uart0-pi5" | sudo tee -a /boot/firmware/config.txt
sudo reboot
```

> **Note:** The config file is at `/boot/firmware/config.txt` on Ubuntu Server 24.04. On older Raspberry Pi OS versions it is at `/boot/config.txt`. Writing to the wrong file has no effect.

After rebooting, verify the UART is available:

```bash
ls /dev/tty* | grep -E "AMA|serial"
# Expected output:
# /dev/ttyAMA0
# /dev/serial0 -> ttyAMA0
```

That's it — **no Bluetooth disabling is needed on Pi 5.**

### Alternative: Different Pin Pair

If you'd rather free up GPIO14/15 for other peripherals, rewire the GPS to a different pin pair and load the matching overlay (`uart2-pi5`, `uart3-pi5`, or `uart4-pi5`). The same `/dev/ttyAMA*` device-permission steps apply — just use the overlay line and physical pins for that UART.

### Alternative: USB Connection

Many NEO-M8N breakout boards can be read over USB (either via an onboard USB-serial bridge or a cheap USB-TTL adapter). The device then shows up as `/dev/ttyUSB0` (already in the `dialout` group by default on Ubuntu), and you skip the overlay/`config.txt` dance entirely — at the cost of an extra cable or adapter.

### Serial Console Cleanup (if needed)

If you see kernel messages or a login prompt appearing on the serial port after enabling the UART, follow these steps to stop the console from using the serial port:

**Step 1: Edit cmdline.txt:**

```bash
sudo nano /boot/firmware/cmdline.txt
```

Remove `console=serial0,115200` (include the trailing space). Use the **Home** key to jump to the start of the line, then delete that token. Save with `Ctrl+O` → Enter → `Ctrl+X`.

**Step 2: Disable serial getty services:**
```bash
sudo systemctl disable serial-getty@ttyAMA0.service
```

**Step 3: Reboot:**
```bash
sudo reboot
```

**Step 4: After reboot, verify GPS is working:**
```bash
ls -la /dev/ttyAMA0
sudo cat /dev/ttyAMA0
```
You should see clean NMEA sentences like `$GPGGA,...` and `$GPRMC,...` streaming in. Press `Ctrl+C` to stop.

---

## Part 3: GPIO Setup with lgpio

Every GPIO peripheral in this project — BTS7960 motor drivers, the HC-SR04 ultrasonic sensor, the buzzer and the status LEDs — is driven through **`lgpio`**, which talks to `/dev/gpiochip*` instead of the legacy `/dev/gpiomem`:

- **No hardware PWM overlay is required.** Motor PWM is generated in software by `lgpio.tx_pwm()` at 1000 Hz, so there is no `dtoverlay=pwm` line and no pin muxing to worry about.
- **No `RPi.GPIO` dependency.** `RPi.GPIO` does not officially support the Pi 5's RP1 south-bridge chip; `geofence_node.py`, `hardware_controller.py` and `motor_controller_node.py` all use `lgpio`.
- Only the **gpiochip device permissions** (Step 2) need to be configured.

### Step 1: Identify the GPIO chip

The Pi 5 exposes the 40-pin header through the RP1 chip. Install the diagnostic tools and look for `pinctrl-rp1`:

```bash
sudo apt install -y gpiod
gpiodetect
# Expected (partial):
# gpiochip4 [pinctrl-rp1] (54 lines)
```

On this Ubuntu 24.04 / Raspberry Pi 5 setup the header is **`gpiochip4`**, which is why `gpio_chip: 4` is the default in `config/hardware_params.yaml`. If your board reports a different number, override it at runtime instead of editing code:

```bash
# One-off override for a node
ros2 run virtual_geofence geofence_node --ros-args -p gpio_chip:=0

# Persistent override for the motor controller: edit gpio_chip in
# src/virtual_geofence/config/hardware_params.yaml
```

### Step 2: GPIO permissions

The nodes use `lgpio` to access `/dev/gpiochip*`. Without the correct permissions you will see one of:

```text
RuntimeError: Failed to open gpiochip
```

```text
PermissionError: [Errno 13] Permission denied: '/dev/gpiochip4'
```

Do **not** run the nodes as root. Configure permissions properly instead.

**Create the `gpio` group and add your user:**

```bash
sudo groupadd -f gpio
sudo usermod -aG gpio $USER
```

**Create a persistent udev rule.** GPIO device nodes are recreated at every boot, so permissions set with `chmod` do not persist:

```bash
sudo tee /etc/udev/rules.d/60-gpiomem.rules > /dev/null <<'EOF'
KERNEL=="gpiomem*", GROUP="gpio", MODE="0660"
KERNEL=="gpiochip*", GROUP="gpio", MODE="0660"
EOF
```

**Reload the rules and reboot.** Group membership changes only apply to new login sessions:

```bash
sudo udevadm control --reload-rules
sudo udevadm trigger
sudo reboot
```

**Verify the permissions:**

```bash
ls -l /dev/gpiochip*
groups
```

Expected output:

```text
crw-rw---- 1 root gpio ... /dev/gpiochip4
...
dialout gpio
```

### Step 3: Smoke-test lgpio (blink the red LED)

With the red LED on GPIO 27 (physical pin 13) in series with 220 Ω to GND:

```bash
cd ~/GEOFENCE
source source_all.bash
python3 - <<'EOF'
import time
import lgpio

h = lgpio.gpiochip_open(4)          # gpiochip4 on the Pi 5 40-pin header
lgpio.gpio_claim_output(h, 27, 0)   # pins MUST be claimed before use

for _ in range(4):
    lgpio.gpio_write(h, 27, 1)
    time.sleep(0.25)
    lgpio.gpio_write(h, 27, 0)
    time.sleep(0.25)

lgpio.gpio_free(h, 27)              # always release pins...
lgpio.gpiochip_close(h)             # ...then close the chip
print("lgpio OK - red LED blinked 4 times")
EOF
```

If that works, `lgpio` is installed correctly and the `gpio` group permissions are right.

> **Note:** `gpioset` / `gpioget` hold a claim on the pins for as long as they run, which conflicts with a running node. Stop the nodes before using the `gpiod` command-line tools, and prefer the `lgpio` snippet above for hardware checks.

### Step 4: systemd services

If you run the nodes via a `systemd` service (see Part 8), the service does not inherit your shell environment or group memberships. Add `SupplementaryGroups=gpio` to the `[Service]` section of the unit so the process can open `/dev/gpiochip*` (then `sudo systemctl daemon-reload` and restart the service):

```ini
[Service]
User=ubuntu
SupplementaryGroups=gpio
```

---

## Part 4: Add the ROS 2 Repository & Install

Check your architecture and Ubuntu codename first:

```bash
dpkg --print-architecture
. /etc/os-release && echo $UBUNTU_CODENAME
```

1. Install prerequisites

```bash
sudo apt update
sudo apt install -y curl gnupg lsb-release ca-certificates
```

2. Add the ROS 2 GPG key (preferred: use gpg dearmor)

```bash
sudo curl -sSL https://raw.githubusercontent.com/ros/rosdistro/master/ros.key | sudo gpg --dearmor -o /usr/share/keyrings/ros-archive-keyring.gpg
```

3. Add the ROS 2 apt repository (this uses your system architecture automatically)

```bash
echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/ros-archive-keyring.gpg] http://packages.ros.org/ros2/ubuntu $(. /etc/os-release && echo $UBUNTU_CODENAME) main" | sudo tee /etc/apt/sources.list.d/ros2.list > /dev/null
sudo apt update
```

4. List available ROS base packages and choose the distro that matches your needs

```bash
apt-cache pkgnames | grep '^ros-.*-ros-base$'
# example result: ros-jazzy-ros-base
```

5. Install ROS 2 base and colcon

```bash
sudo apt install -y ros-jazzy-ros-base python3-colcon-common-extensions
```

> **Important:** `nmea_navsat_driver` is **not** part of `ros-base`. `geofence_launch.py` starts
> `nmea_serial_driver` from it, so install it here — otherwise the launch aborts with
> *package 'nmea_navsat_driver' not found*:
>
> ```bash
> sudo apt install -y ros-jazzy-nmea-navsat-driver
> source /opt/ros/jazzy/setup.bash
> ```
>
> With a bare `ros-base` install (driver missing), `geofence_launch.py` now skips the GPS
> driver with a warning and still starts `geofence_node` and `motor_controller_node`, so you
> can test using a simulated fix:
>
> ```bash
> ros2 run virtual_geofence mock_gps_publisher
> ```

6. Install `uv` for dependency management

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
source $HOME/.local/bin/env
```

After installation, source ROS and verify:

```bash
source /opt/ros/jazzy/setup.bash
echo $ROS_DISTRO
which ros2
ros2 --help
python3 -m colcon --help
```

---

## Part 5: Set Up the ROS 2 Workspace

The project is organized as a standard ROS 2 workspace. Dependencies are managed by `uv` at the root, while the package lives in `src/`.

```bash
# 1. Clone the repository
git clone https://github.com/al-chris/GEOFENCE ~/GEOFENCE
cd ~/GEOFENCE

# 2. Initialize the Python environment
# We use --system-site-packages to bridge the venv with ROS 2 system libraries
uv venv --system-site-packages
uv pip install -r requirements.txt
```

> **Do not upgrade NumPy to 2.x in this venv.** Because `.venv` comes first on `PYTHONPATH`,
> its NumPy shadows the system NumPy that `apt`-installed ROS packages are built against.
> `nmea_serial_driver` imports `/usr/lib/python3/dist-packages/transforms3d` (0.3.1), which
> calls `np.maximum_sctype` — removed in NumPy 2.0 — so the GPS driver dies right after start
> with `AttributeError: 'np.maximum_sctype' was removed in the NumPy 2.0 release`.
> `requirements.txt` therefore pins `numpy<2` (Ubuntu 24.04 / Jazzy ship NumPy 1.26.4).
> If you already installed 2.x, downgrade it:
>
> ```bash
> uv pip install 'numpy<2'
> ```

---

## Part 6: Build the ROS 2 Workspace

```bash
source /opt/ros/jazzy/setup.bash
cd ~/GEOFENCE
colcon build --symlink-install
```

You should see `Summary: 1 package finished`.

### Sourcing the Environment

To simplify sourcing ROS, the virtual environment, and your workspace, use the provided helper script:

```bash
source source_all.bash
```

This script ensures that `PYTHONPATH` is correctly set so that ROS nodes can find libraries (like `filterpy`) installed in your `.venv`.

---

## Part 7: Run the Code (Testing Mode)

There are three ways to test the geofence logic: using mock nodes, the full Gazebo simulation, or real hardware. **Always ensure you have run `source source_all.bash` first.**

### Method A: Mock Nodes (No Simulation)

To test the system without a physical GPS or a 3D simulation, open two separate terminal windows.

#### Terminal 1: Start the Geofence Node
```bash
ros2 run virtual_geofence geofence_node
```

#### Terminal 2: Start the Mock GPS
```bash
ros2 run virtual_geofence mock_gps_publisher
```

### Method B: Gazebo Simulation (Recommended for Visual Testing)

This method provides a full 3D environment with a robot spawning inside the field.

```bash
ros2 launch virtual_geofence sim_launch.py
```

**What to Expect:**
*   Gazebo window opens with the `field.sdf` world.
*   The `lawnmower` model spawns at `(0, -22)`.
*   The `geofence_node` starts and listens to the `/gps/fix` topic published by the Gazebo GPS sensor.
*   You can drive the robot using a teleop node (see below) to test boundary breaches.

### Method C: Manual Control (Teleop)

To drive the robot manually using keyboard commands, use the `teleop_twist_keyboard` ROS 2 package. This allows you to publish velocity commands directly to the robot's `/cmd_vel` topic.

#### Step 1: Start the Simulation or Hardware

Ensure your robot is running in Gazebo or on the Pi:

**Simulation:**
```bash
ros2 launch virtual_geofence sim_launch.py
```

**Hardware:**
```bash
ros2 run virtual_geofence geofence_node --ros-args --params-file src/virtual_geofence/config/boundary.yaml
```

#### Step 2: Launch Teleop in a New Terminal

Open a second terminal, source the environment, and run the keyboard teleop node:

```bash
source source_all.bash
ros2 run teleop_twist_keyboard teleop_twist_keyboard
```

**Expected output:**
```
Reading from keyboard
Use arrow keys to move forward/backward and turn.
q/z : increase/decrease max speeds by 10%
w/x : increase/decrease only linear speed by 10%
e/c : increase/decrease only angular speed by 10%
space key, s : force stop
CTRL-C to quit
```

#### Keyboard Controls

**Make sure the teleop terminal window is in focus (click on it) before pressing keys.**

| Key | Action | Description |
| :--- | :--- | :--- |
| **`i`** | **Forward** | Moves straight ahead. |
| **`,`** | **Backward** | Moves straight back. |
| **`j`** | **Rotate Left** | Spins the robot left in place. |
| **`l`** | **Rotate Right** | Spins the robot right in place. |
| **`u`** | **Curve Left** | Drives forward while turning left. |
| **`o`** | **Curve Right** | Drives forward while turning right. |
| **`m`** | **Curve Back Left** | Reverses while turning left. |
| **`.`** | **Curve Back Right**| Reverses while turning right. |
| **`k`** or **Space** | **Stop** | Instantly stops all movement. |
| **`q` / `z`** | **Speed +/-** | Increases or decreases both linear and angular speed. |
| **`w` / `x`** | **Linear +/-** | Increases or decreases linear speed only. |
| **`e` / `c`** | **Angular +/-** | Increases or decreases rotation speed only. |
| **Ctrl+C** | **Quit** | Exits the teleop controller. |

#### What to Expect

1. **Real-time movement:** The `lawnmower` model in Gazebo (or the physical robot) responds immediately to your key presses.
2. **Geofence Enforcement:** If you drive the robot outside the boundary defined in `boundary.yaml`, the `geofence_node` will detect the breach, publish a stop command to `/cmd_vel`, and the robot will cease moving. You will see a `[WARN] BOUNDARY CROSSED` message in the node terminal.
3. **Indicator Feedback:** On hardware, the Red LED and Buzzer will activate when the boundary is crossed.

#### Troubleshooting

| Issue | Cause | Solution |
|-------|-------|----------|
| **Keys don't respond** | Teleop terminal not in focus | Click on the teleop terminal window to give it keyboard focus |
| **`teleop_twist_keyboard` command not found** | Package not installed | Run `sudo apt install ros-jazzy-teleop-twist-keyboard` |
| **`package 'nmea_navsat_driver' not found`** | GPS driver package missing — it is not included in `ros-base` | Run `sudo apt install ros-jazzy-nmea-navsat-driver`, then `source /opt/ros/jazzy/setup.bash` and rebuild/re-source the workspace |
| **`AttributeError: np.maximum_sctype was removed in the NumPy 2.0 release`** and `nmea_serial_driver` exits immediately | NumPy 2.x in `.venv` shadows the system NumPy that `transforms3d` 0.3.1 expects | Run `uv pip install 'numpy<2'`, then `source source_all.bash` and relaunch |
| **Robot doesn't move** | Geofence node is blocking | Check if you are already outside the boundary. Re-enter the boundary or update `boundary.yaml`. |
| **Robot moves erratically** | Conflicting publishers | Ensure no other nodes (like an autonomous planner) are publishing to `/cmd_vel` |

---

### What to Expect (Mock Nodes)

Once both are running, look at the Geofence Node terminal. You should see the Kalman Filter initialising, followed by live coordinate tracking. After a few seconds, the mock GPS will drift outside the coordinates defined in your `boundary.yaml`, and you will see:

```
[INFO] Kalman filter initialised at (7.518500, 4.517700)
[INFO] Stop command published to /cmd_vel
[WARN] BOUNDARY CROSSED → OUTSIDE | (7.518500, 4.517700)
```

---

## Hardware Note

### GPS Module: NEO-M8N Wiring

Connect the NEO-M8N GPS module to the Raspberry Pi 5 GPIO header as follows:

| NEO-M8N Pin | Raspberry Pi Pin | GPIO |
|-------------|------------------|------|
| TX | Pin 10 (RXD) | GPIO 15 |
| RX | Pin 8 (TXD) | GPIO 14 |
| VCC | Pin 2 (5V) | — |
| GND | Pin 6 (GND) | — |

> The UART is available on `/dev/ttyAMA0` after applying the Bluetooth disable overlay in Part 2.

### Serial device permissions

If you receive "Permission denied" when opening `/dev/ttyAMA0`, ensure your user is in the `dialout` group (most serial devices are owned by `dialout`) and create a persistent udev rule to keep the device group and mode correct:

```bash
sudo tee /etc/udev/rules.d/60-ttyAMA0.rules > /dev/null <<'EOF'
KERNEL=="ttyAMA0", SUBSYSTEM=="tty", GROUP="dialout", MODE="0660"
EOF
sudo udevadm control --reload-rules
sudo udevadm trigger --name-match=ttyAMA0
ls -l /dev/ttyAMA0
```

If a background service (e.g. `gpsd`) is using the port, stop it before testing:

```bash
sudo systemctl stop gpsd.socket gpsd || true
sudo fuser -v /dev/ttyAMA0 || true
```

### LED & Buzzer Wiring

Wire the LEDs and buzzer as follows (these are the `geofence_node.py` lgpio defaults, and can be changed with the `buzzer_pin`, `red_led_pin` and `green_led_pin` ROS parameters):

| Component | GPIO |
|-----------|------|
| Buzzer | GPIO 17 |
| Red LED | GPIO 27 |
| Green LED | GPIO 22 |

### BTS7960 Motor Driver & HC-SR04 Ultrasonic Wiring

The system supports differential drive control using BTS7960 drivers and obstacle detection using HC-SR04 ultrasonic distance sensors. For complete schematics, voltage dividers, and pinouts, see [WIRING.md](file:///C:/Users/PC/Documents/PROJECTS/GEOFENCE/WIRING.md) and [GPIO-Pinout-Diagram.png](file:///C:/Users/PC/Documents/PROJECTS/GEOFENCE/GPIO-Pinout-Diagram.png).

| Component | BCM GPIO | Notes |
|---|---|---|
| Left Motor RPWM | GPIO 12 | Forward PWM |
| Left Motor LPWM | GPIO 13 | Reverse PWM |
| Left Motor R_EN | GPIO 20 | Forward enable |
| Left Motor L_EN | GPIO 21 | Reverse enable |
| Right Motor RPWM | GPIO 18 | Forward PWM |
| Right Motor LPWM | GPIO 19 | Reverse PWM |
| Right Motor R_EN | GPIO 16 | Forward enable |
| Right Motor L_EN | GPIO 26 | Reverse enable |
| Front Ultrasonic TRIG | GPIO 23 | 10µs trigger pulse |
| Front Ultrasonic ECHO | GPIO 24 | **Via 1kΩ/2kΩ voltage divider to 3.3V** |

### Rapid Hardware Testing (Standalone)

Before launching ROS 2 or running full automation, test each subsystem in isolation. These scripts talk to the GPIO header directly through `lgpio` (they do not need ROS running):

```bash
source source_all.bash

# 1. Buzzer + status LEDs (GPIO 17 / 27 / 22) - easiest first check
python3 scripts/test_indicators.py

# 2. Front HC-SR04 ultrasonic sensor (TRIG GPIO 23, ECHO GPIO 24)
python3 scripts/test_ultrasonic.py

# 3. BTS7960 motors - ramps forward then reverse (put the robot on blocks!)
python3 scripts/test_motors.py
# ...one side only:
python3 scripts/test_motors.py --motor left
```

Once the individual parts work, use the combined motor + ultrasonic utility:

```bash
# Read sensors only (motors disabled - safe test)
python3 scripts/motor_ultrasonic_control.py --mode status

# Ramp motors forward and reverse (keep wheels off ground on blocks)
python3 scripts/motor_ultrasonic_control.py --mode ramp

# Obstacle avoidance reactive test
python3 scripts/motor_ultrasonic_control.py --mode obstacle --speed 40 --stop-cm 20
```

> **Troubleshooting:** If a script fails with `RuntimeError: Failed to open gpiochip` or `PermissionError: ... '/dev/gpiochip4'`, go back to Part 3 (Step 2) and fix the `gpio` group / udev permissions. If it fails because the chip number is different, pass `--chip <n>` (run `gpiodetect` to find it).

### Running on Physical Hardware (Full ROS 2 Stack)

Start the entire hardware system including GPS driver, geofence monitor, and motor controller:

```bash
source source_all.bash
ros2 launch virtual_geofence geofence_launch.py
```

This launches:
1. `nmea_serial_driver` on `/dev/ttyAMA0` for NEO-M8N GPS.
2. `geofence_node` to enforce the polygon boundary and publish zero velocity to `/cmd_vel` upon breach.
3. `motor_controller_node` to translate `/cmd_vel` into differential PWM for the BTS7960 drivers and stop upon obstacle detection.

To launch only the motor controller node independently:
```bash
ros2 launch virtual_geofence motor_control_launch.py
```

---

## Part 8: Running as a systemd service (optional)

You can run `geofence_node` as a systemd unit so it starts on boot and is supervised. A template unit is provided in the repository at `systemd/geofence.service` — edit it to replace `youruser` and the workspace paths with your actual username and workspace location on the Pi.

Install and enable the service (run these on the Pi):

```bash
# copy the unit into place
sudo cp systemd/geofence.service /etc/systemd/system/geofence.service

# reload systemd and start the service
sudo systemctl daemon-reload
sudo systemctl enable --now geofence.service

# check status and logs
sudo systemctl status geofence.service -l
sudo journalctl -u geofence.service -f
```

Important notes:
- Ensure the `User` and `WorkingDirectory` fields in the unit are correct for your system.
- GPIO is accessed through `lgpio`, which opens `/dev/gpiochip*` rather than `/dev/gpiomem`. The unit already includes `SupplementaryGroups=gpio` so the service process inherits access to the chip devices when the user is in the `gpio` group (see Part 3). If you change the user, make sure that account is a member of `gpio`.
- If it is not already set, pass the GPIO chip number to the node in the unit's `ExecStart` (`-p gpio_chip:=4` for the Pi 5 header) and check `gpiodetect` if the chip number differs on your board.
- If you prefer the service to run under `root` (not recommended), remove `User`/`Group` and drop `SupplementaryGroups=gpio` accordingly.

After enabling the service, verify GPIO access with `ls -l /dev/gpiochip*` and that the node logs show `lgpio ready on gpiochip4` plus the Kalman filter initialising on the first GPS fix.

---

## Part 9: Simulation Setup (Laptop/PC - WSL2)

**Note: Use WSL2 (Windows Subsystem for Linux) with WSLg for best performance.**

### 1. Install ROS2 Jazzy Desktop
If you are on a PC, you should install the `desktop` version of ROS2 to get Gazebo and RViz.
```bash
sudo apt update && sudo apt install ros-jazzy-desktop ros-jazzy-ros-gz -y
```

### 2. Configure Python Environment (uv)
We use `uv` for local dependency management. It must be configured to see the system ROS2 packages.
```bash
# In the project root (GEOFENCE)
rm -rf .venv
uv venv --system-site-packages
uv sync
```

### 3. Enable GPU Acceleration (WSL2)
By default, WSL might use software rendering. To enable hardware acceleration for your GPU:
```bash
# Check current renderer (should not be llvmpipe)
glxinfo -B | grep "OpenGL renderer"

# If needed, force D3D12 (NVIDIA/AMD/Intel)
echo "export LIBGL_ALWAYS_SOFTWARE=false" >> ~/.bashrc
echo "export GALLIUM_DRIVER=d3d12" >> ~/.bashrc
source ~/.bashrc
```

### 4. Build and Run
```bash
cd ~/GEOFENCE
colcon build --symlink-install
source source_all.bash
ros2 launch virtual_geofence sim_launch.py
```
