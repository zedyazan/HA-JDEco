# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.0.1] - 2026-09-19

### Added
- Automatic Session Recovery: Built-in detection and auto re-authentication when the JDECo WCF session expires (code 1021) or server disconnects, eliminating the need for external reload automations.
- State Retention on Transient Glitches: Coordinator retains the last valid meter readings during temporary network or Cloudflare connectivity drops before raising errors.
- Clean Uninstall: Implemented async_remove_entry to automatically clean up persisted cryptographic storage when the integration is deleted.
- Arabic Localization: Added comprehensive Arabic translation (translations/ar.json) for seamless setup in Home Assistant.
- Recharge Financial Breakdown: 7 detailed financial and tariff metrics including Clean Energy Rate (kWh / NIS), Effective Tariff (ILS / kWh), Pure Electricity Cost, Fees, and VAT.
- Options Flow Support: Dynamic polling interval configuration directly from Home Assistant UI.

### Changed
- Corrected Remaining Prepaid Credit unit of measurement to kWh (kilowatt-hours) with SensorDeviceClass.ENERGY.
- Increased HTTP POST retry attempts to 3 with exponential backoff for resilience against Cloudflare socket drops.
- Masked phone numbers and credentials in all logs.

## [1.0.0] - 2026-09-13

### Added
- Initial release of JDECo Home Assistant integration.
- Dynamic device binding and SMS One-Time Password (OTP) verification.
- AES-256-GCM + RSA-2048 hybrid encryption implementation matching JDECo mobile app protocol.
- 29+ sensors for smart meter readings, prepaid balance, last recharge, and tariff parameters.
- Manual Check Credit button to trigger immediate balance refresh.
- Full diagnostics dump support.
