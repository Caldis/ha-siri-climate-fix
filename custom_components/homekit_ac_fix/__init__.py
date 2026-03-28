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
    except ImportError:
        _LOGGER.error(
            "HomeKit AC Fix: cannot import homekit components — "
            "is the homekit integration installed?"
        )
        return False

    if not hasattr(Thermostat, "_set_chars"):
        _LOGGER.error(
            "HomeKit AC Fix: Thermostat._set_chars not found — "
            "HA version may be incompatible, patch not applied"
        )
        return False

    original_set_chars = Thermostat._set_chars

    def patched_set_chars(self: Any, char_values: dict[str, Any]) -> None:
        """Intercept AUTO(3) when unsupported: call climate.turn_on."""
        target_hc = char_values.get(CHAR_TARGET_HEATING_COOLING)

        if (
            target_hc is not None
            and target_hc == HC_HEAT_COOL_AUTO
            and HC_HEAT_COOL_AUTO not in self.hc_homekit_to_hass
        ):
            # Siri sent AUTO, device doesn't support it.
            # Original would fall back to heat. We call turn_on instead.
            state = self.hass.states.get(self.entity_id)

            if state and state.state in ("off", "unavailable", "unknown"):
                _LOGGER.info(
                    "HomeKit AC Fix: AUTO requested for %s (off), "
                    "using turn_on instead of heat fallback",
                    self.entity_id,
                )
                self.async_call_service(
                    "climate",
                    "turn_on",
                    {"entity_id": self.entity_id},
                    f"{CHAR_TARGET_HEATING_COOLING} to {target_hc} (turn_on)",
                )
            else:
                _LOGGER.debug(
                    "HomeKit AC Fix: AUTO requested for %s (already %s), "
                    "no mode change needed",
                    self.entity_id,
                    state.state if state else "unknown",
                )

            # Strip the mode key; let original handle remaining chars
            # (temperature, humidity, etc.) without triggering fallback.
            remaining = {
                k: v
                for k, v in char_values.items()
                if k != CHAR_TARGET_HEATING_COOLING
            }
            if remaining:
                original_set_chars(self, remaining)
            return

        # Not an AUTO fallback — pass through unchanged.
        original_set_chars(self, char_values)

    Thermostat._set_chars = patched_set_chars
    _LOGGER.info(
        "HomeKit AC Fix: Thermostat._set_chars patched — "
        "AUTO fallback will use climate.turn_on"
    )
    return True
