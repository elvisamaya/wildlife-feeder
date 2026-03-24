// feeder.ino — wildlife feeder v2
// ATmega328P / Arduino Uno
// last edited: 2025-08-02
//
// Wiring:
//   PIR signal  -> D2  (INT0)
//   motor IN1   -> D5
//   motor IN2   -> D6
//   status LED  -> D13 (built-in)
//
// Serial at 9600 baud. Log format mirrors feeder_harness.py expectations.
// TODO: add RTC for timestamped logs without host PC

#include <Arduino.h>

// ── pins ──────────────────────────────────────────────────────────────────────
static const uint8_t PIN_PIR    = 2;
static const uint8_t PIN_IN1    = 5;
static const uint8_t PIN_IN2    = 6;
static const uint8_t PIN_LED    = 13;

// ── tunable constants ─────────────────────────────────────────────────────────
static const uint16_t MOTOR_MS      = 400;   // dispense run time
static const uint32_t COOLDOWN_MS   = 30000; // lockout after a dispense
static const uint16_t PIR_THRESH    = 600;   // raw ADC sanity-check (not used for trigger, just logged)
static const uint8_t  DISPENSE_QTY  = 1;     // future: multi-dispense bursts

// ── state ─────────────────────────────────────────────────────────────────────
static volatile bool  g_pir_fired  = false;
static uint32_t       g_last_feed  = 0;
static bool           g_armed      = false;

// ── ISR ───────────────────────────────────────────────────────────────────────
void IRAM_ATTR on_pir_rise() {
    g_pir_fired = true;
}

// ── helpers ───────────────────────────────────────────────────────────────────
static String uptime_str() {
    uint32_t s = millis() / 1000;
    char buf[9];
    snprintf(buf, sizeof(buf), "%02lu:%02lu:%02lu",
             s / 3600, (s % 3600) / 60, s % 60);
    return String(buf);
}

static void motor_run(uint16_t ms) {
    digitalWrite(PIN_IN1, HIGH);
    digitalWrite(PIN_IN2, LOW);
    delay(ms);
    digitalWrite(PIN_IN1, LOW);
    digitalWrite(PIN_IN2, LOW);
}

static void dispense() {
    Serial.print(F("[FEED] motor_ms="));
    Serial.print(MOTOR_MS);
    Serial.print(F(" qty="));
    Serial.println(DISPENSE_QTY);

    digitalWrite(PIN_LED, HIGH);
    motor_run(MOTOR_MS);
    digitalWrite(PIN_LED, LOW);

    Serial.println(F("[INFO] dispense_ok=1"));
}

// ── setup ─────────────────────────────────────────────────────────────────────
void setup() {
    Serial.begin(9600);
    while (!Serial) {}   // wait for USB CDC on 32u4 boards; instant on 328P

    pinMode(PIN_PIR,  INPUT);
    pinMode(PIN_IN1,  OUTPUT);
    pinMode(PIN_IN2,  OUTPUT);
    pinMode(PIN_LED,  OUTPUT);

    digitalWrite(PIN_IN1, LOW);
    digitalWrite(PIN_IN2, LOW);
    digitalWrite(PIN_LED, LOW);

    Serial.print(F("[BOOT] fw=0.4.1 chip=328P\n"));

    // HC-SR501 needs ~30 s to stabilise; blink LED while waiting
    Serial.print(F("[INFO] pir_warmup_s=30\n"));
    for (uint8_t i = 0; i < 30; i++) {
        digitalWrite(PIN_LED, i % 2);
        delay(1000);
    }
    digitalWrite(PIN_LED, LOW);

    Serial.print(F("[INFO] thresh="));
    Serial.print(PIR_THRESH);
    Serial.print(F(" cooldown_s="));
    Serial.println(COOLDOWN_MS / 1000);

    attachInterrupt(digitalPinToInterrupt(PIN_PIR), on_pir_rise, RISING);

    g_armed = true;
    Serial.println(F("[INFO] armed"));
}

// ── loop ──────────────────────────────────────────────────────────────────────
void loop() {
    if (!g_pir_fired) return;
    g_pir_fired = false;   // clear flag before checking — avoids re-entry race

    uint16_t raw = analogRead(A0);   // not the trigger source, just logged
    Serial.print(F("[PIR]  state=1 raw="));
    Serial.print(raw);
    Serial.print(F(" thresh="));
    Serial.println(PIR_THRESH);

    uint32_t now = millis();

    if (!g_armed || (now - g_last_feed) < COOLDOWN_MS) {
        Serial.println(F("[INFO] suppressed — cooldown active"));
        return;
    }

    g_last_feed = now;
    dispense();

    // cooldown — re-arm when done
    Serial.print(F("[INFO] cooldown_s="));
    Serial.print(COOLDOWN_MS / 1000);
    Serial.print(F(" uptime="));
    Serial.println(uptime_str());

    delay(COOLDOWN_MS);

    // drain any spurious ISR triggers that fired during cooldown
    g_pir_fired = false;

    uint16_t raw2 = analogRead(A0);
    Serial.print(F("[PIR]  state=0 raw="));
    Serial.print(raw2);
    Serial.print(F(" thresh="));
    Serial.println(PIR_THRESH);

    Serial.println(F("[INFO] armed"));
}
