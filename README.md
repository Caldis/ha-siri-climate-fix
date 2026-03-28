# ha-siri-climate-fix

> **Fix: Siri "Turn on AC" always defaults to Heat mode in Home Assistant HomeKit Bridge**

Home Assistant custom integration that fixes the HomeKit bridge thermostat always
falling back to **heat** when Siri turns on an air conditioner.

## The Problem

When you say **"Hey Siri, turn on the AC"** (or 打开空调), HomeKit sends
`TargetHeatingCoolingState = AUTO(3)`. Since most AC / climate devices don't
support `heat_cool` mode, the Home Assistant HomeKit bridge falls back to
**heat** — every single time, regardless of what mode (cool, dry, fan) the AC
was last using.

This is a [known, long-standing issue](https://github.com/home-assistant/core/issues/60203)
in the HA HomeKit bridge (`HC_HEAT_COOL_PREFER_HEAT` fallback in
`type_thermostats.py`). It affects **all climate devices** exposed via the
HomeKit bridge that don't support auto/heat_cool mode — including Xiaomi/Mi Home,
Midea, Daikin, Gree, Haier, and many more.

## The Fix

This integration patches the bridge's thermostat handler at a single point: when
AUTO is requested but not supported, it calls `climate.turn_on` instead of
falling back to heat. This lets the AC firmware use its own remembered mode.

```
Before (broken):
  Siri "turn on AC" → AUTO(3) → bridge fallback → set_hvac_mode(heat) → always heat 😡

After (fixed):
  Siri "turn on AC" → AUTO(3) → patch intercepts → climate.turn_on → AC uses its last mode ✓
```

**Zero config. Zero extra entities. Zero delay. No more unwanted heating.**

## Installation

1. Copy `custom_components/homekit_ac_fix/` to your HA config's `custom_components/` directory
2. Add to `configuration.yaml`:
   ```yaml
   homekit_ac_fix:
   ```
3. Restart Home Assistant
4. Verify in logs: `Thermostat._set_chars patched — AUTO fallback will use turn_on`

## How it works

The patch is minimal (~60 lines) and surgical:

- **What it patches**: `Thermostat._set_chars` in `homeassistant.components.homekit.type_thermostats`
- **When it intercepts**: Only when `TargetHeatingCoolingState == AUTO(3)` AND the device doesn't support `heat_cool`
- **What it does**: Calls `climate.turn_on` (no mode specified → AC firmware decides)
- **Everything else**: Passes through to the original handler unchanged

Safety checks included:
- Verifies `ClimateEntityFeature.TURN_ON` is supported before calling
- Falls back to original behavior if entity state is unavailable
- Guards against double-patching on reload
- Fails gracefully if HA updates change the internal API

## Compatibility

- **Home Assistant**: 2024.1+ (tested on 2025.8.2)
- **Climate devices**: Any device exposed via the HomeKit bridge that doesn't support `heat_cool` mode
- **Known working**: Xiaomi/Mi Home AC, and should work with any climate integration
- **Failure mode**: If HA updates break the patch, it logs a warning and falls back to the original heat behavior — your system keeps working

## Why not just use an automation?

| | Automation workaround | This integration |
|---|---|---|
| Delay | 500ms+ (race conditions possible) | None (synchronous) |
| State flicker | Brief heat→cool visible | No flicker |
| Season safety | Edge cases at cool↔heat transition | No issue (firmware decides) |
| Setup | input_text helpers + 2 automations per AC | One line in config |
| Scope | Must list each entity | All climate entities automatically |

## Details

See [docs/ANALYSIS.md](docs/ANALYSIS.md) for the full root cause analysis,
HA source code walkthrough, community research, and comparison with all
alternative approaches considered.

## Related Issues

- [home-assistant/core#60203](https://github.com/home-assistant/core/issues/60203) — Siri requests AUTO even when not valid
- [home-assistant/core#18254](https://github.com/home-assistant/core/issues/18254) — HomeKit generic thermostat auto mode
- [HA Community: HeaterCooler accessory type support](https://community.home-assistant.io/t/heater-cooler-accessory-type-support/343778)

## License

MIT
