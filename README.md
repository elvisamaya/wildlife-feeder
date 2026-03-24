# 🐦 wildlife-feeder

Motion-triggered wildlife feeder running on an Arduino Uno — PIR sensor fires an interrupt, runs a small motor to dispense food, then locks out for a cooldown period. Logs everything over serial in a structured format that pairs with the Python test harness.

---

## Hardware

| Component | Part |
|---|---|
| Microcontroller | Arduino Uno (ATmega328P) |
| Motion sensor | HC-SR501 PIR |
| Motor driver | L298N dual H-bridge |
| Power | 9V barrel jack |

### Wiring
```
PIR signal  → D2  (INT0)
Motor IN1   → D5
Motor IN2   → D6
Status LED  → D13 (built-in)
```

---

## Files
```
feeder.ino          Arduino sketch — flash this to the board
feeder_harness.py   Python test harness — run on your PC over USB
```

---

## Getting Started

### Flash the sketch

Open `feeder.ino` in the Arduino IDE, select **Arduino Uno** as the board, and upload.  
The onboard LED will blink for ~30 s while the PIR warms up, then stay off when armed.

### Run the harness
```bash
pip install pyserial

# list available ports
python feeder_harness.py --list-ports

# connect and log to csv
python feeder_harness.py --port /dev/tty.usbmodem1101 --csv events.csv

# offline simulation (no hardware needed)
python feeder_harness.py --simulate --interval 4 --count 8
```

### Serial output
```
00:00:01  INFO     [    142 ms]  [BOOT] fw=0.4.1 chip=328P
00:00:01  INFO     [    285 ms]  [INFO] thresh=600 cooldown_s=30
00:00:31  INFO     [  30401 ms]  [INFO] armed
00:00:35  INFO     [  34812 ms]  [PIR]  state=1 raw=847 thresh=600
00:00:35  INFO     [  34823 ms]  [FEED] motor_ms=400 qty=1
00:00:35  INFO     [  35230 ms]  [INFO] dispense_ok=1
```

---

## Configuration

Tunable constants are at the top of `feeder.ino`:

| Constant | Default | Description |
|---|---|---|
| `MOTOR_MS` | `400` | Motor run time in ms |
| `COOLDOWN_MS` | `30000` | Lockout period after dispense |
| `PIR_THRESH` | `600` | ADC threshold logged alongside triggers |
