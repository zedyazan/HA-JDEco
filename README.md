# JDECo Electricity — Home Assistant Custom Integration

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://github.com/hacs/default)
[![Validate](https://github.com/jdeco-ha/core/actions/workflows/validate.yml/badge.svg)](https://github.com/jdeco-ha/core/actions/workflows/validate.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![HA Version](https://img.shields.io/badge/Home%20Assistant-2024.1%2B-blue.svg)](https://www.home-assistant.io)

An independent, full-featured Home Assistant integration for **Jerusalem District Electricity Company (JDECo / شركة كهرباء محافظة القدس)** smart meters and prepaid electricity accounts.

Reverse-engineered from the official JDECo mobile app wire protocol, this integration provides live smart meter readings, remaining credit balances, consumption analytics, recharge history, and transparent tariff financial breakdown.

---

## ⚡ Key Features

- **🔋 Real-time Credit & Smart Meter:** Tracks remaining prepaid balance (accurately reported in **kWh**), current smart meter reading, and meter connection status.
- **💰 Financial & Tariff Breakdown:**
  - **Clean Energy Rate (`kWh / NIS`):** How much clean electricity 1 NIS buys before municipal fees and VAT (~1.80 kWh/NIS).
  - **Effective Energy Rate (`kWh / NIS`):** How much net electricity you actually receive per 1 NIS paid (~1.37 kWh/NIS).
  - **Clean Tariff (`ILS / kWh`):** Pure base electricity tariff (~0.555 ILS/kWh).
  - **Effective Tariff (`ILS / kWh`):** True all-in cost per kWh including 16% Palestinian VAT and municipal service fees (~0.730 ILS/kWh).
- **📊 Consumption History:** Calculates current month energy (kWh), current month cost (ILS), current year consumption (kWh), and seasonal averages (summer/winter).
- **🔄 Resilient Auto-Recovery:** Automatic re-authentication when WCF sessions expire (code 1021) and intelligent retry with exponential backoff on Cloudflare socket drops. No external automations required!
- **🛡️ 100% Standalone & Clean Uninstall:** Zero YAML configuration needed. Setup and options configured entirely through the UI. Complete cleanup of persistent storage upon deletion.
- **🌍 Bilingual Support:** Full English and Arabic (`العربية`) translations for config and options flows.
- **🔒 Privacy First:** Multi-user dynamic device registration with client-side RSA-2048 keypair generation. All credentials and encryption keys are stored locally within Home Assistant.

---

## 📦 Installation

### Method 1: Via HACS (Recommended)

1. Ensure **HACS** is installed in your Home Assistant instance.
2. In Home Assistant, navigate to **HACS** → **Integrations**.
3. Click the three dots in the top-right corner and select **Custom repositories**.
4. Add this repository URL, choose **Integration** as the category, and click **Add**.
5. Find **JDECo Electricity** in the list and click **Download**.
6. Restart Home Assistant.

### Method 2: Manual Installation

1. Download the latest release `.zip` or clone this repository.
2. Copy the `custom_components/jdeco/` folder into your Home Assistant `<config>/custom_components/` directory.
3. Restart Home Assistant.

---

## 🚀 Setup & Configuration

1. In Home Assistant, go to **Settings** → **Devices & Services** → **Add Integration**.
2. Search for **JDECo Electricity**.
3. **Step 1 — Credentials:**
   - **Phone Number:** Your registered Palestinian mobile number (e.g. `05XXXXXXXX`).
   - **Password:** Your JDECo portal password.
   - **Polling Interval:** Desired update interval in minutes (default: `60`, min: `30`).
4. **Step 2 — Device Authorization (One-Time SMS OTP):**
   - JDECo will send a 6-digit SMS verification code to your phone.
   - Enter the code in the prompt to register Home Assistant as an authorized device.
   - *Note: Once registered, your device authorization token is persisted securely. You will not need to enter SMS codes again for subsequent logins!*

> 💡 **User Tips & Suggestions:**
> - **Keep your phone handy:** The SMS verification code is only requested during initial setup.
> - **Cooldown:** JDECo servers enforce rate limiting. Avoid rapid repeated login attempts; wait 60 seconds between tries.
> - **Polling Interval:** A 60-minute polling interval is recommended to balance data freshness with Cloudflare WAF limits. You can adjust this anytime under **Settings** → **Devices & Services** → **JDECo** → **Configure**.
> - **Manual Refresh:** Need the absolute latest balance immediately after recharging? Simply press the **Check Credit** button entity!

---

## 📈 Sensors & Entities Catalog

### ⚡ Electricity & Meter Sensors
| Entity ID | Name | Unit | Description |
|-----------|------|:----:|-------------|
| `sensor.jdeco_remaining_credit` | Remaining Credit | `kWh` | Remaining prepaid balance on meter |
| `sensor.jdeco_current_reading` | Current Reading | `kWh` | Live cumulative smart meter reading |
| `sensor.jdeco_meter_reading_time` | Meter Reading Time | timestamp | Time of latest smart meter reading |
| `sensor.jdeco_monthly_kwh` | Monthly Consumption | `kWh` | Total energy recharged in current month |
| `sensor.jdeco_monthly_cost` | Monthly Cost | `ILS` | Total amount spent in current month |
| `sensor.jdeco_yearly_kwh` | Yearly Consumption | `kWh` | Cumulative recharges for current calendar year |
| `sensor.jdeco_meter_general_avg` | Average Monthly | `kWh` | General monthly average consumption |
| `sensor.jdeco_meter_summer_avg` | Summer Average | `kWh` | Historical summer average |
| `sensor.jdeco_meter_winter_avg` | Winter Average | `kWh` | Historical winter average |

### 🏷️ Last Recharge & Tariff Analysis
| Entity ID | Name | Unit | Description |
|-----------|------|:----:|-------------|
| `sensor.jdeco_last_recharge_amount` | Last Recharge Amount | `ILS` | Total gross amount paid |
| `sensor.jdeco_last_recharge_kwh` | Last Recharge Energy | `kWh` | Energy credited from last recharge |
| `sensor.jdeco_last_recharge_pure_cost`| Pure Energy Cost | `ILS` | Cost of electricity before fees & VAT |
| `sensor.jdeco_last_recharge_vat` | Last Recharge VAT | `ILS` | Palestinian 16% Value Added Tax |
| `sensor.jdeco_last_recharge_fees` | Last Recharge Fees | `ILS` | Municipal waste & fixed service fees |
| `sensor.jdeco_clean_kwh_per_nis` | Clean Energy Rate | `kWh/ILS` | Pure energy yield per 1 NIS (~1.80) |
| `sensor.jdeco_effective_kwh_per_nis`| Effective Energy Rate | `kWh/ILS`| Real energy yield per 1 NIS paid (~1.37) |
| `sensor.jdeco_clean_tariff` | Clean Tariff | `ILS/kWh` | Base electricity rate per kWh (~0.55) |
| `sensor.jdeco_effective_tariff` | Effective Tariff | `ILS/kWh` | All-in real cost per kWh paid (~0.73) |
| `sensor.jdeco_last_sts_token` | Last STS Token | string | 20-digit recharge token |

### 🎛️ Controls & Binary Sensors
- **Button:** `button.jdeco_check_credit` (instant manual refresh on demand)
- **Binary Sensors:**
  - `binary_sensor.jdeco_smart_meter` (Smart meter enabled)
  - `binary_sensor.jdeco_prepaid_meter` (Prepaid tariff type)
  - `binary_sensor.jdeco_low_credit_warning` (Alert when remaining credit is critically low)
  - `binary_sensor.jdeco_can_charge_remotely` (Remote recharge capability)
  - `binary_sensor.jdeco_estimated_reading` (Reading status flag)

---

## 🔒 Security & Privacy

- **Hybrid Cryptography:** Direct implementation of JDECo's wire protocol combining **AES-256-GCM** and **RSA-2048 (PKCS#1 v1.5)**.
- **Local Key Storage:** Private RSA keys and device tokens are stored locally in Home Assistant (`.storage/jdeco_keys_*`) with strict file permissions.
- **No Cloud Third Parties:** All communications go directly from your Home Assistant host to JDECo's secure WCF endpoint over HTTPS (port 2083).
- **PII Scrubbing:** Logs automatically mask phone numbers and session tokens.

---

## ⚠️ Disclaimer

This project is an independent open-source contribution developed for personal home automation and community use. It is **not** affiliated with, authorized, maintained, or endorsed by the Jerusalem District Electricity Company (JDECo) or any of its subsidiaries. All trademarks and registered trademarks belong to their respective owners.
