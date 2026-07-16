# Example automations

SEMS only calculates — *you* decide what happens with the numbers. Below
are ready-to-paste examples, from simple to smart. Replace the entity ids
of switches with your own.

## 1. Run the dishwasher during one of the day's best hours

`sensor.sems_rank` ranks the current hour from 1 (worst) to 24 (best), so
"above 19" means: one of the **5 best hours** of the coming day.

```yaml
automation:
  - alias: "Dishwasher during a top-5 hour"
    trigger:
      - platform: numeric_state
        entity_id: sensor.sems_rank
        above: 19
    condition:
      # Only if you loaded it and flipped this helper on:
      - condition: state
        entity_id: input_boolean.dishwasher_ready
        state: "on"
    action:
      - service: switch.turn_on
        target:
          entity_id: switch.dishwasher
      - service: input_boolean.turn_off
        target:
          entity_id: input_boolean.dishwasher_ready
```

> Tip: create the `input_boolean.dishwasher_ready` helper via Settings →
> Devices & services → Helpers. Flip it on when you load the machine; SEMS
> picks the moment.

## 2. Turn the PV inverter off when power is free

When the all-in price is negative you *pay* to export. Better to stop
producing for a while.

```yaml
automation:
  - alias: "PV inverter off during free power"
    trigger:
      - platform: state
        entity_id: binary_sensor.sems_free_power
        to: "on"
    action:
      - service: switch.turn_off
        target:
          entity_id: switch.pv_inverter

  - alias: "PV inverter back on after free power"
    trigger:
      - platform: state
        entity_id: binary_sensor.sems_free_power
        to: "off"
    action:
      - service: switch.turn_on
        target:
          entity_id: switch.pv_inverter
```

## 3. Heat the boiler in the top half of the day

The relative score is a percentage: 100% = the best hour of the window.

```yaml
automation:
  - alias: "Boiler when the hour is better than average"
    trigger:
      - platform: numeric_state
        entity_id: sensor.sems_relative_score
        above: 50
        for: "00:05:00"
    action:
      - service: switch.turn_on
        target:
          entity_id: switch.boiler
```

## 4. Charge the EV only during the best hours

Combine a high relative score (the top of the day) with a free-power
override:

```yaml
automation:
  - alias: "EV charging during good hours"
    trigger:
      - platform: numeric_state
        entity_id: sensor.sems_relative_score
        above: 80
      - platform: state
        entity_id: binary_sensor.sems_free_power
        to: "on"
    action:
      - service: switch.turn_on
        target:
          entity_id: switch.ev_charger
```

## Notes for automation builders

- **Rank is per calendar day.** Since v0.4.0 `sensor.sems_rank` ranks the
  current hour within today, on a stable 1–24 scale, so "rank above 19"
  means "one of today's 5 best hours" at any time — morning included.
  (Before v0.4.0 it used a rolling window whose scale shrank to 14 in the
  morning, so that threshold could never fire then.)
- **Everything updates hourly.** Numeric-state triggers fire when the value
  crosses the threshold, which happens on the hour.
- **The `scores_24h` attribute** on `sensor.sems_relative_score` contains
  the whole window, including *future* hours — advanced users can template
  on it, e.g. "is a much better hour coming within 3 hours?".
