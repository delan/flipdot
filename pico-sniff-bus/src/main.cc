#include <Arduino.h>

void setup() {
    pinMode(LED_BUILTIN, OUTPUT);

    Serial1.setTX(0);
    Serial1.setRX(1);
    Serial1.begin(4800);
}

void serialEvent1() {
    Serial.print("rx");
    while (Serial1.available() > 0) {
        Serial.printf(" %02X", Serial1.read());
    }
    Serial.println("h");
}

void loop() {
    static bool led = false;
    digitalWrite(LED_BUILTIN, led = !led);
    delay(500);

    // usb cdc tx on the pico dies unless there is periodic activity.
    // i have been developing for the rp2040 for over a year now,
    // and i still have no fucking idea why this is broken.
    Serial.print("\r");
}
