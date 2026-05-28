/*
  ┌─────────────────────────────────────────────────┐
  │  Nasal Breathing Monitor — Raw Data Output       │
  │  Board : XIAO nRF52840 Plus (mbed package)       │
  │  Mic 1 : Yellow wire → A0 (D0)                  │
  │  Mic 2 : Blue wire   → A1 (D1)                  │
  │                                                  │
  │  Philosophy: collect everything, decide nothing  │
  │  All thresholding/downsampling in Python         │
  │                                                  │
  │  Output format (one line per reading):           │
  │  {"t":1234567,"seq":42,"m1":2048,"m2":2031,     │
  │   "temp":124}                                   │
  │                                                  │
  │  Keys:                                           │
  │    t    = millis() ms since board boot          │
  │    seq  = packet counter, detects dropped pkts  │
  │    m1   = mic1 raw ADC yellow (0–4095)          │
  │    m2   = mic2 raw ADC blue   (0–4095)          │
  │    temp = chip die temp raw (divide by 4 = °C)  │
  │                                                  │
  │  Rate: ~100–200 Hz, limited by Serial at 115200 │
  │  Downsample to target Hz in Python pipeline     │
  └─────────────────────────────────────────────────┘
*/

// ── PINS ──────────────────────────────────────────
#define MIC_YELLOW        A0    // Mic 1 — Yellow wire
#define MIC_BLUE          A1    // Mic 2 — Blue wire

// ── SETTINGS ──────────────────────────────────────
#define BAUD_RATE         115200

// ── GLOBALS ───────────────────────────────────────
uint32_t seqCounter = 0;

// ─────────────────────────────────────────────────
void setup() {
  Serial.begin(BAUD_RATE);
  delay(3000);

  analogReference(AR_INTERNAL2V4);
  analogReadResolution(12);   // 0–4095

  // Startup message
  // Python uses boot_ms to establish time anchor
  Serial.print("{\"status\":\"ready\","
               "\"board\":\"xiao_nrf52840\","
               "\"boot_ms\":");
  Serial.print(millis());
  Serial.println("}");
}

// ─────────────────────────────────────────────────
// Read nRF52840 internal chip temperature
// Returns raw value in 0.25°C units
// divide by 4.0 in Python to get °C
// ─────────────────────────────────────────────────
int32_t readChipTemp() {
  NRF_TEMP->TASKS_START = 1;
  while (NRF_TEMP->EVENTS_DATARDY == 0);
  NRF_TEMP->EVENTS_DATARDY = 0;
  int32_t raw = NRF_TEMP->TEMP;
  NRF_TEMP->TASKS_STOP = 1;
  return raw;
}

// ─────────────────────────────────────────────────
void loop() {

  // ── Read sensors ──────────────────────────────
  int      v1   = analogRead(MIC_YELLOW);
  int      v2   = analogRead(MIC_BLUE);
  uint32_t t_ms = millis();
  int32_t  temp = readChipTemp();

  seqCounter++;

  // ── Send raw JSON — no classification ─────────
  // All decisions happen in Python analysis layer
  Serial.print("{\"t\":");
  Serial.print(t_ms);
  Serial.print(",\"seq\":");
  Serial.print(seqCounter);
  Serial.print(",\"m1\":");
  Serial.print(v1);
  Serial.print(",\"m2\":");
  Serial.print(v2);
  Serial.print(",\"temp\":");
  Serial.print(temp);
  Serial.println("}");
}
