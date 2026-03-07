# Koubachi Plant Sensor — Home Assistant Integration

Integrates [Koubachi](https://www.koubachi.com/) Wi-Fi plant sensors with Home Assistant. The sensor pushes encrypted readings directly to HA's built-in HTTP server — no cloud, no separate process, no sensor reconfiguration.

## How it works

The Koubachi sensor resolves `api.koubachi.com` via DNS and POSTs AES-128-CBC encrypted readings to port 80. This integration registers HTTP endpoints inside HA's built-in web server. Add a local DNS override pointing `api.koubachi.com` to your HA host and the sensor starts delivering data — no changes to the sensor required.

## Requirements

- Home Assistant 2023.1 or later
- Python package `cryptography>=3.4` (installed automatically)
- A local DNS server that can override `api.koubachi.com` (e.g. Pi-hole, AdGuard Home, or your router's custom DNS)
- Your sensor's MAC address and 16-byte AES encryption key
- Port 80 reachable on your HA host (setup varies by install type — see below)
- A Wi-Fi network named `koubachi` with the correct password (the sensor only connects to this SSID)

---

## Installation

### Option A — HACS (recommended)

1. In HACS, go to **Integrations** → ⋮ → **Custom repositories**
2. Add this repository URL, category **Integration**
3. Search for **Koubachi** and install
4. Restart Home Assistant

### Option B — Manual

Copy the `custom_components/koubachi/` folder into your HA config directory:

```
<config>/custom_components/koubachi/
```

Restart Home Assistant.

---

## Network setup by install type

The Koubachi sensor always connects to `api.koubachi.com` on **port 80**. You need to redirect that traffic to HA. The steps differ depending on how HA is installed.

### Home Assistant OS (HAOS) — recommended

HAOS runs on a dedicated machine with nothing else on port 80. Configure HA's HTTP server to listen on port 80 directly:

```yaml
# configuration.yaml
http:
  server_port: 80
```

Restart HA after making this change. Then add the [DNS override](#dns-override) and you're done.

### Home Assistant Container (plain Docker)

HA listens on port 8123 by default. You need to either expose port 80 from the container or use a reverse proxy.

**Option 1 — Run HA on port 80** (simplest): configure HA to use port 80 and expose it:

```yaml
# configuration.yaml
http:
  server_port: 80
```

```yaml
# docker-compose.yml
services:
  homeassistant:
    ports:
      - "80:80"     # Koubachi + HA web UI
      - "8123:8123" # keep if you also access HA on the default port
```

**Option 2 — Reverse proxy** (if port 80 is already taken by another service): route requests for `api.koubachi.com` to the HA container. Example using Traefik with a dynamic config file (e.g. `traefik/dynamic/koubachi.yml`):

```yaml
http:
  routers:
    koubachi:
      rule: "Host(`api.koubachi.com`)"
      service: koubachi
      entryPoints:
        - web
  services:
    koubachi:
      loadBalancer:
        servers:
          - url: "http://<ha-container-name>:8123"
```

Replace `<ha-container-name>` with the hostname or IP of your HA container as seen from the Traefik container.

### Runtipi / Traefik-managed Docker

Runtipi uses Traefik on port 80 for its dashboard. Use the Traefik dynamic config approach described above. Place the file in your Traefik dynamic config directory (check your `traefik.yml` for the `file.directory` setting).

### Home Assistant Supervised

Behaves like HAOS — set `server_port: 80` in `configuration.yaml`. Verify nothing else on the host is using port 80 first.

---

## DNS override

Add a local DNS record pointing `api.koubachi.com` to your HA host's IP address. This is required regardless of install type.

**Pi-hole / AdGuard Home** — add a custom DNS record:
```
api.koubachi.com → <ha-ip>
```

**Router (e.g. OpenWrt / dnsmasq)** — add to the dnsmasq config:
```
address=/api.koubachi.com/<ha-ip>
```

Once active, the sensor's next check-in reaches Home Assistant automatically.

---

## Adding a device

1. Go to **Settings → Devices & Services → Add Integration**
2. Search for **Koubachi**
3. Fill in the form:

   | Field | Example | Notes |
   |-------|---------|-------|
   | Device name | `Living Room Ficus` | Friendly label for the plant |
   | MAC address | `aabbccddeeff` | 12 hex chars, no colons |
   | Encryption key | `00112233445566778899aabbccddeeff` | 32 hex chars (16 bytes) |
   | Calibration JSON | `{"RN171_SMU_GAIN": 0.9}` | Optional, use `{}` if unknown |

4. Click **Submit**. Sensor entities appear immediately (state: *unavailable* until the first reading arrives).

To update the device name or calibration parameters later, go to the integration entry and choose **Reconfigure**. The MAC address and encryption key cannot be changed after initial setup.

---

## Sensor entities

For each configured device the integration creates the following entities:

| Entity | Unit | Description |
|--------|------|-------------|
| `sensor.<name>_temperature` | °C | Air temperature |
| `sensor.<name>_soil_temperature` | °C | Soil temperature |
| `sensor.<name>_soil_moisture` | integer (0–6) | Soil moisture on Koubachi scale |
| `sensor.<name>_light` | lx | Ambient light (whole number) |
| `sensor.<name>_battery` | % | Battery level (2× AA alkaline) |
| `sensor.<name>_rssi` | dBm | Wi-Fi signal strength |

---

## Plant monitoring

The [Plant Monitor](https://github.com/Olen/homeassistant-plant) custom integration by Olen pairs well with this integration. It provides a plant card with health status, threshold alerts, and plant species lookup from the OpenPlantBook database.

### Setup

1. Install **Plant Monitor** via HACS
2. Go to **Settings → Devices & Services → Add Integration** and search for **Plant Monitor**
3. Create a plant and assign the Koubachi sensor entities:

   | Plant Monitor field | Koubachi entity |
   |---------------------|-----------------|
   | Temperature | `sensor.<name>_temperature` |
   | Soil moisture | `sensor.<name>_soil_moisture` |
   | Illuminance | `sensor.<name>_light` |
   | Battery | `sensor.<name>_battery` |

4. Set thresholds manually or look up your plant species in OpenPlantBook to auto-populate them.

> **Note on soil moisture scale:** Koubachi reports soil moisture on a 0–6 scale (0 = dry, 6 = saturated). Set your Plant Monitor min/max thresholds accordingly (e.g. min: 2, max: 5).

---

## Calibration parameters

Calibration adjusts raw ADC readings to physical units. If you have values from the original Koubachi cloud config, paste them as a JSON object in the calibration field. Common keys:

| Key | Affects |
|-----|---------|
| `RN171_SMU_GAIN` | Temperature, light, and soil moisture scaling |
| `RN171_SMU_DC_OFFSET` | Temperature offset correction |
| `LM94022_TEMPERATURE_OFFSET` | Additional temperature offset |
| `SFH3710_DC_OFFSET_CORRECTION` | Light sensor offset |
| `SOIL_MOISTURE_MIN` | Soil moisture zero-point |
| `SOIL_MOISTURE_DISCONTINUITY` | Soil moisture scale factor |

Missing parameters default to `0` — readings will still be produced but accuracy may be reduced.

---

## Troubleshooting

**Entities stay unavailable after setup**
Verify `api.koubachi.com` resolves to your HA IP from the sensor's network (`nslookup api.koubachi.com` from a device on the same network). Also check that port 80 is reachable on your HA host.

**"Unknown device" errors in HA logs**
The MAC address in the request doesn't match any configured entry. Verify the MAC you entered matches the sensor's actual MAC (check your router's DHCP leases or the label on the sensor).

**Decryption errors in logs**
The encryption key is wrong. Double-check that it's exactly 32 hex characters and matches the key for this specific sensor.

**Sensor sends data but values look wrong**
Try adding calibration parameters. The raw ADC-to-physical conversion assumes specific hardware parameters that vary between sensor batches.

**Light sensor always reads 0**
The `SFH3710_DC_OFFSET_CORRECTION` and `RN171_SMU_GAIN` calibration parameters are likely missing. Without `RN171_SMU_GAIN` the formula multiplies by zero. Add these values to the calibration JSON if available.
