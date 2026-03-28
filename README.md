# homekit-ac-fix

Home Assistant custom integration that fixes the HomeKit bridge's AC mode fallback.

## Problem

When you tell Siri "turn on AC" (打开空调), HomeKit sends `AUTO(3)`. Since most AC units
don't support `heat_cool` mode, the HA HomeKit bridge falls back to **heat** — every time,
regardless of what mode the AC was last using.

## Solution

This integration monkey-patches the bridge's thermostat handler at a single point: when
AUTO is requested but not supported, it calls `climate.turn_on` instead of falling back to
heat. This lets the AC firmware use its own remembered mode (cool, heat, dry, etc.).

**Zero config, zero extra entities, zero delay.**

## Installation

1. Copy `custom_components/homekit_ac_fix/` to your HA config's `custom_components/` directory
2. Add to `configuration.yaml`:
   ```yaml
   homekit_ac_fix:
   ```
3. Restart Home Assistant

## How it works

```
Before (broken):
  Siri "turn on AC" → AUTO(3) → bridge fallback → climate.set_hvac_mode(heat) → always heat

After (fixed):
  Siri "turn on AC" → AUTO(3) → patch intercepts → climate.turn_on → AC uses firmware mode
```

The patch only intercepts one specific case: `AUTO(3)` when the device doesn't support it.
All other HomeKit operations pass through unchanged.

## Compatibility

- **Home Assistant**: 2024.1+ (tested on 2025.8.2)
- **Climate devices**: Any device exposed via the HomeKit bridge that doesn't support `heat_cool`
- **Failure mode**: If HA updates break the patch, it fails gracefully — logs an error and
  falls back to the original heat behavior

## Details

See [docs/ANALYSIS.md](docs/ANALYSIS.md) for full root cause analysis, community research,
and comparison with alternative approaches.
