# homekit-ac-fix

HA custom integration that monkey-patches the HomeKit bridge thermostat handler
to fix the AUTO→heat fallback when Siri turns on an AC.

## Project structure

```
custom_components/homekit_ac_fix/   → deployable integration (copy to HA config)
docs/                               → problem analysis, community research
```

## Conventions

- Keep the integration minimal — one file, one patch point
- No external dependencies beyond HA core
- Compatibility check before patching (fail gracefully)
- Default branch: master
