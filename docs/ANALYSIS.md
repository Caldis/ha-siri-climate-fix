# Problem Analysis: HomeKit Bridge AC Mode Fallback

## Symptom

Siri "打开空调" (turn on AC) always activates the air conditioner in **heat** mode,
regardless of the last mode used. This affects all climate devices exposed via
Home Assistant's HomeKit bridge that don't support `heat_cool` / `auto` mode.

## Root Cause

### The command flow

```
Siri "打开空调"
  → HomeKit sends TargetHeatingCoolingState = AUTO(3)
  → HA HomeKit bridge receives AUTO(3)
  → Bridge checks: does device support heat_cool?
  → NO → fallback logic in _set_chars
  → HC_HEAT_COOL_PREFER_HEAT = [AUTO, HEAT, COOL, OFF]
  → Picks first supported: HEAT
  → climate.set_hvac_mode(heat)
```

### The fallback code

Source: `homeassistant/components/homekit/type_thermostats.py`

```python
if target_hc not in self.hc_homekit_to_hass:
    hc_target_temp = char_values.get(CHAR_TARGET_TEMPERATURE)
    hc_current_temp = _get_current_temperature(state, self._unit)
    hc_fallback_order = HC_HEAT_COOL_PREFER_HEAT       # default
    if (
        hc_target_temp is not None
        and hc_current_temp is not None
        and hc_target_temp < hc_current_temp
    ):
        hc_fallback_order = HC_HEAT_COOL_PREFER_COOL    # only if temp sent
    for hc_fallback in hc_fallback_order:
        if hc_fallback in self.hc_homekit_to_hass:
            self.char_target_heat_cool.value = target_hc = hc_fallback
            break
```

The "smart" temperature comparison only works when Siri also sends a target
temperature. "打开空调" sends **no temperature** → `hc_target_temp` is `None`
→ comparison never triggers → **always falls back to heat**.

### Xiaomi AC firmware behavior

When powered on, Xiaomi AC firmware briefly reports its hardware-remembered mode
(e.g. `cool`) before the bridge's `set_hvac_mode(heat)` overrides it.

Observed state sequence (from HA history):

```
08:02:24.747  off
08:07:01.126  cool    ← firmware reports remembered mode
08:07:01.399  heat    ← bridge fallback overrides (~270ms later)
```

This means:
1. The AC firmware already remembers the correct mode
2. The bridge actively destroys it by sending heat

## Community Research (2026-03-28)

### GitHub Issues

| Issue | Description | Status |
|-------|------------|--------|
| [#60203](https://github.com/home-assistant/core/issues/60203) | Siri sends AUTO when not valid | PR #60220 fixed acceptance but not fallback |
| [#18254](https://github.com/home-assistant/core/issues/18254) | Earliest report (2018) | Fallback logic added but defaults to heat |
| [#20667](https://github.com/home-assistant/core/issues/20667) | HomeKit shows all 4 modes | Closed as "by design" (SDK limitation) |
| [Discussion #3115](https://github.com/orgs/home-assistant/discussions/3115) | Request HeaterCooler type | Unanswered |

### Community Feature Requests

- **HeaterCooler accessory type**: Most requested fix. HomeKit's HeaterCooler
  type is more appropriate for ACs than Thermostat. Not implemented, no plan.
- **Configurable fallback preference**: Never proposed as a PR.

### Workarounds found

| Approach | Evaluation |
|----------|-----------|
| Bind temperature sensor | Only helps when Siri sends target temp |
| Input Boolean + automation | Coarse, separate switch per AC |
| Template climate wrapper | Adds `heat_cool` mode but causes TARGET_TEMPERATURE_RANGE UI issue |
| Homebridge | Different stack entirely |
| Modify HA source | Overwritten on update |

**No one has published a monkey-patch custom integration approach.**

## Solution: homekit_ac_fix

### Approach

Monkey-patch `Thermostat._set_chars` at runtime. When AUTO(3) is received and
not supported by the device, call `climate.turn_on` instead of falling back to
heat. This lets the AC firmware use its hardware-remembered mode.

### Why this works

- `climate.turn_on` doesn't specify an HVAC mode
- The AC firmware already remembers its last mode
- The bridge's state callback will pick up the actual mode after turn_on

### Advantages over automation-based approach

| Aspect | Automation (v3) | Monkey-patch |
|--------|----------------|-------------|
| Timing | 500ms delay + race conditions | Synchronous, no delay |
| Season safety | Edge case at cool↔heat transition | No issue (firmware decides) |
| State flicker | Brief heat→cool visible | No flicker |
| Maintenance | YAML automations + input_text helpers | Single Python file |
| Scope | Per-entity trigger lists | All climate entities automatically |

### Known limitations

1. **HA update risk**: If `_set_chars` signature changes, patch won't apply
   (fails gracefully to original behavior, logged as error)
2. **"Set to auto" via Siri**: Also intercepted — skips mode change since
   device can't support auto anyway (acceptable behavior)
3. **AC already on + Siri "turn on"**: No mode change (correct — AC stays
   in current mode)

## Previous automation-based solution (still deployed as fallback)

The automation approach (separate repo, deployed via HA REST/WS API) uses:
- 3x `input_text` helpers to store last HVAC mode per AC
- Automation "Save" to record mode changes
- Automation "Restore" to revert heat fallback

This remains deployed as a safety net. If the custom integration is active,
the bridge won't send heat, so the Restore automation's trigger never fires.

## Entities

| Room | Climate Entity | Last Mode Helper |
|------|---------------|-----------------|
| 客厅 | climate.xiaomi_cn_282443357_mc5 | input_text.ac_last_mode_xiaomi_cn_282443357_mc5 |
| 主卧 | climate.xiaomi_cn_282443143_mc5 | input_text.ac_last_mode_xiaomi_cn_282443143_mc5 |
| 次卧 | climate.xiaomi_cn_270652700_mc5 | input_text.ac_last_mode_xiaomi_cn_270652700_mc5 |

## HA Environment

- Version: 2025.8.2
- Installation: HA OS (UTM VM on Mac mini)
- HomeKit Bridge: built-in integration
- Climate integration: Xiaomi MIOT
