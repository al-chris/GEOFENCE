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

- Under **Choose Device**, select **Raspberry Pi 3**.
- Under **Choose OS**, do not select the default Raspberry Pi OS. Instead:
  - Click **Other general-purpose OS**
  - Click **Ubuntu**
  - Select **Ubuntu Server 24.04 LTS (64-bit)** (or the latest LTS version available).

> **Note:** While 32-bit uses slightly less RAM, 64-bit is the standard going forward and is fully supported on the Pi 3.

### 3. Configure Settings

Click **Choose Storage** and select your SD card. Click **Next**.

When prompted about OS customization settings, click **Edit Settings** and configure the following:

- **General tab:** Set a hostname, username, and password. Configure Wi-Fi if you want the Pi to connect to your network automatically on first boot.
- **Services tab:** Enable SSH. This allows you to control the Pi from your main computer, which is especially useful for server installs without a monitor.

Click **Save**, then **Yes** to apply settings.

### 4. Write to the SD Card

Click **Yes** when warned that all existing data will be erased. Wait for the Imager to download, write, and verify the image. Once it says **Write Successful**, remove the SD card.

### 5. First Boot

Insert the SD card into the Raspberry Pi 3 and power it on.

> **Be patient:** The first boot takes several minutes as Ubuntu configures network settings and resizes the filesystem.

Log in using the username and password you set in the Imager.

---

## Part 2: Raspberry Pi 3 — Bluetooth/UART Conflict Fix

### The Problem

On the Raspberry Pi 3, the hardware UART (`/dev/ttyAMA0`) is assigned to the Bluetooth module by default. This leaves only the mini-UART (`/dev/ttyS0`) for the GPIO pins (14 & 15), which is clock-speed dependent and unreliable for GPS communication.

Symptoms:
- Running `ls /dev/tty*` shows `/dev/ttyS0` but no `/dev/ttyAMA0`
- GPS module receives no data or corrupted data over serial
- `sudo cat /dev/ttyS0` shows nothing or garbage characters

### The Fix

Add the `disable-bt` device tree overlay to `/boot/firmware/config.txt`:

```bash
echo "dtoverlay=disable-bt" | sudo tee -a /boot/firmware/config.txt
sudo reboot
```

> **Note:** On older Raspberry Pi OS versions the config file is at `/boot/config.txt`. On Ubuntu Server 24.04 and Raspberry Pi OS Bookworm/Trixie it is at `/boot/firmware/config.txt`. Writing to the wrong file has no effect.

After rebooting, verify the UART is free:

```bash
ls /dev/tty* | grep -E "AMA|serial"
# Expected output:
# /dev/ttyAMA0
# /dev/serial0 -> ttyAMA0
```

### Why It Works

The `disable-bt` overlay detaches Bluetooth from the hardware UART and hands `/dev/ttyAMA0` back to the GPIO header. Bluetooth is disabled but the full, stable UART is now available for the GPS module on pins 8 (TX) and 10 (RX).

### Side Effects

- Bluetooth is fully disabled after applying this overlay.

If, after disabling Bluetooth, you see kernel messages or a login prompt repeatedly appearing on the serial console (many lines of HELP: loglevel... or similar), follow these steps to stop the console from using the serial port and to disable serial getty services:

**Step 1: Edit cmdline.txt:**

```bash
sudo nano /boot/firmware/cmdline.txt
```

**From:**
```
console=serial0,115200 multipath=off dwc_otg.lpm_enable=0 console=tty1 root=LABEL=writable rootfstype=ext4 rootwait fix>
```

**To:**
```
multipath=off dwc_otg.lpm_enable=0 console=tty1 root=LABEL=writable rootfstype=ext4 rootwait fix>
```

Use the **Home** key to jump to the start of the line, then delete `console=serial0,115200 ` (include the trailing space). Save with `Ctrl+O` → Enter → `Ctrl+X`.

**Step 2: Disable serial getty services:**
```bash
sudo systemctl disable serial-getty@ttyAMA0.service
sudo systemctl disable serial-getty@ttyS0.service
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

## Part 3: GPIO Setup & Verification

Install the GPIO tools:

```bash
sudo apt install -y gpiod
```

Test that GPIO is working by toggling a pin (this sets GPIO 27 high — you can connect an LED to verify):

```bash
gpioset gpiochip0 27=1
```

If you get a permission denied error, add your user to the `gpio` group and reboot:

```bash
sudo usermod -aG gpio $USER
sudo reboot
```

If `/dev/gpiomem` is still root-only, you can temporarily give the `gpio` group access:

```bash
sudo chown root:gpio /dev/gpiomem
sudo chmod 660 /dev/gpiomem
```

### Make this persistent (recommended)

The device node is recreated at boot; use a udev rule so `/dev/gpiomem` keeps the `gpio` group and correct permissions:

```bash
sudo tee /etc/udev/rules.d/60-gpiomem.rules > /dev/null <<'EOF'
KERNEL=="gpiomem", SUBSYSTEM=="misc", GROUP="gpio", MODE="0660"
EOF

# Reload udev rules and apply immediately
sudo udevadm control --reload-rules
sudo udevadm trigger --name-match=gpiomem

# Verify permissions
ls -l /dev/gpiomem

# Make sure the user running the node is in the gpio group (re-login required)
sudo usermod -aG gpio $USER
```

If you run the node via a `systemd` service, add `SupplementaryGroups=gpio` to the `[Service]` section of the unit so the service inherits the group (then `sudo systemctl daemon-reload` and restart the service).

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

Connect the NEO-M8N GPS module to the Raspberry Pi 3 GPIO header as follows:

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

Wire the LEDs and buzzer as follows (based on `geofence_node.py`):

| Component | GPIO |
|-----------|------|
| Buzzer | GPIO 17 |
| Red LED | GPIO 27 |
| Green LED | GPIO 22 |

### Running on Physical Hardware

Start the node (no `sudo` required if GPIO permissions are configured):

```bash
sudo chown root:gpio /dev/gpiomem
sudo chmod 660 /dev/gpiomem
ros2 run virtual_geofence geofence_node --ros-args --params-file src/virtual_geofence/config/boundary.yaml
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
- The unit already includes `SupplementaryGroups=gpio` so the service process inherits access to `/dev/gpiomem` when the user is in the `gpio` group. If you change the user, make sure that account is a member of `gpio`.
- If you prefer the service to run under `root` (not recommended), remove `User`/`Group` and drop `SupplementaryGroups=gpio` accordingly.

After enabling the service, verify GPIO access with `ls -l /dev/gpiomem` and that the node logs show the Kalman filter initialising on the first GPS fix.

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
