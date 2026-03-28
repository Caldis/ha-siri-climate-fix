"""HomeKit AC Fix: replace heat fallback with climate.turn_on for AUTO mode.

When Siri says "turn on AC", HomeKit sends TargetHeatingCoolingState=AUTO(3).
If the climate device doesn't support auto/heat_cool, the HA HomeKit bridge
falls back to heat via HC_HEAT_COOL_PREFER_HEAT. This patch intercepts that
fallback and calls climate.turn_on instead, letting the AC firmware decide
which HVAC mode to use (its hardware-remembered last mode).

Patch target: homeassistant.components.homekit.type_thermostats.Thermostat._set_chars
Compatibility: Home Assistant 2024.1+ (tested on 2025.8.2)
"""

import logging
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.typing import ConfigType

_LOGGER = logging.getLogger(__name__)

DOMAIN = "homekit_ac_fix"


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Patch HomeKit bridge Thermostat._set_chars to fix AUTO fallback."""
    try:
        from homeassistant.components.homekit.type_thermostats import (
            Thermostat,
            HC_HEAT_COOL_AUTO,
        )
        from homeassistant.components.homekit.const import (
            CHAR_TARGET_HEATING_COOLING,
        )
        from homeassistant.components.climate import ClimateEntityFeature
    except ImportError:
        _LOGGER.warning(
            "Cannot import homekit components — homekit integration not "
            "installed or HA version incompatible. Patch not applied."
        )
        return True  # non-essential; don't mark integration as failed

    if not hasattr(Thermostat, "_set_chars"):
        _LOGGER.warning(
            "Thermostat._set_chars not found — HA version may be "
            "incompatible. Patch not applied."
        )
        return True

    # Guard against double-patching on integration reload.
    if getattr(Thermostat._set_chars, "_homekit_ac_fix_patched", False):
        _LOGGER.debug("Already patched, skipping")
        return True

    original_set_chars = Thermostat._set_chars

    # Both async_setup and _set_chars run in the HA event loop (main thread),
    # so the attribute assignment below is safe — no concurrent access.
    def patched_set_chars(self: Any, char_values: dict[str, Any]) -> None:
        """Intercept AUTO(3) when unsupported: call climate.turn_on."""
        target_hc = char_values.get(CHAR_TARGET_HEATING_COOLING)

        if (
            target_hc is not None
            and target_hc == HC_HEAT_COOL_AUTO
            and HC_HEAT_COOL_AUTO not in self.hc_homekit_to_hass
        ):
            state = self.hass.states.get(self.entity_id)

            # If entity state is unavailable, fall back to original behavior.
            if state is None:
                _LOGGER.warning(
                    "Cannot get state for %s, falling back to original",
                    self.entity_id,
                )
                original_set_chars(self, char_values)
                return

            if state.state == "off":
                features = state.attributes.get("supported_features", 0)
                if features & ClimateEntityFeature.TURN_ON:
                    _LOGGER.info(
                        "AUTO requested for %s (off) — using turn_on",
                        self.entity_id,
                    )
                    self.async_call_service(
                        "climate",
                        "turn_on",
                        {"entity_id": self.entity_id},
                        f"{CHAR_TARGET_HEATING_COOLING} to"
                        f" {target_hc} (turn_on)",
                    )
                else:
                    # Device doesn't advertise TURN_ON; let bridge do its
                    # original fallback — at least the AC will turn on.
                    _LOGGER.warning(
                        "%s does not support turn_on, "
                        "falling back to original",
                        self.entity_id,
                    )
                    original_set_chars(self, char_values)
                    return
            else:
                # Device already on — no mode change needed.
                _LOGGER.debug(
                    "AUTO requested for %s (already %s), skipping",
                    self.entity_id,
                    state.state,
                )

            # Strip the mode key; forward remaining chars (temperature, etc.)
            remaining = {
                k: v
                for k, v in char_values.items()
                if k != CHAR_TARGET_HEATING_COOLING
            }
            if remaining:
                _LOGGER.debug(
                    "Forwarding remaining chars for %s: %s",
                    self.entity_id,
                    list(remaining.keys()),
                )
                original_set_chars(self, remaining)
            return

        # Not an AUTO fallback — pass through unchanged.
        original_set_chars(self, char_values)

    patched_set_chars._homekit_ac_fix_patched = True  # type: ignore[attr-defined]
    Thermostat._set_chars = patched_set_chars  # type: ignore[assignment]
    _LOGGER.info("Thermostat._set_chars patched — AUTO fallback will use turn_on")
    return True
