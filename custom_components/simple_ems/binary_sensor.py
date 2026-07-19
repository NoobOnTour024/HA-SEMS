"""The SEMS binary sensors.

* ``binary_sensor.sems_free_power`` — ON when the current ALL-IN price is
  below the configured free-power threshold. It is deliberately derived
  from the price itself, never from the score.
* ``binary_sensor.sems_best_2h_block`` (and 3h, 4h) — ON while the best
  consecutive 2/3/4-hour run of the coming window starts in the current
  block. Made for appliances that need more than one block to finish
  (dishwasher, washing machine): trigger the automation when the sensor
  turns ON. The attributes always show when the best run is planned, so
  you can also automate on the start time directly.
* ``binary_sensor.sems_pause_now`` — the mirror image: ON during the worst
  blocks of the day, for devices you want to switch OFF rather than on.
  The pauses are deliberately spread out, so a freezer is never left off
  long enough to thaw. Off unless you set "pause hours per day".
"""

from __future__ import annotations

from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import BLOCK_DURATIONS_HOURS, DOMAIN
from .coordinator import SemsCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Create the SEMS binary sensors for this config entry."""
    coordinator: SemsCoordinator = hass.data[DOMAIN][entry.entry_id]
    entities: list[BinarySensorEntity] = [
        SemsFreePowerBinarySensor(coordinator, entry)
    ]
    for duration_hours in BLOCK_DURATIONS_HOURS:
        entities.append(SemsBestBlockBinarySensor(coordinator, entry, duration_hours))
    entities.append(SemsPauseBinarySensor(coordinator, entry))
    async_add_entities(entities)


class SemsBinarySensorBase(CoordinatorEntity[SemsCoordinator], BinarySensorEntity):
    """Common plumbing: device grouping and naming."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: SemsCoordinator, entry: ConfigEntry, key: str) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_{key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name="SEMS",
            manufacturer="SEMS",
            model="Simple Energy Management System",
        )


class SemsFreePowerBinarySensor(SemsBinarySensorBase):
    """ON when power is currently 'free' (all-in price below the threshold)."""

    _attr_name = "Free power"
    _attr_icon = "mdi:gift-outline"

    def __init__(self, coordinator: SemsCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry, "free_power")

    @property
    def is_on(self) -> bool:
        # Computed by the coordinator as: current all-in price < threshold.
        return bool(self.coordinator.data["free_power"])

    @property
    def extra_state_attributes(self) -> dict:
        return {
            "current_price": round(self.coordinator.data["current"]["price"], 5),
            "threshold": self.coordinator.free_threshold,
        }


class SemsBestBlockBinarySensor(SemsBinarySensorBase):
    """ON while the best N-hour run of the window starts right now.

    "Best" means: the consecutive run of N hours with the highest average
    score within the known data. Because the window rolls forward every
    block, the planned start can shift when new prices arrive — the
    attributes always show the current plan.
    """

    _attr_icon = "mdi:timer-play-outline"

    def __init__(
        self, coordinator: SemsCoordinator, entry: ConfigEntry, duration_hours: int
    ) -> None:
        super().__init__(coordinator, entry, f"best_{duration_hours}h_block")
        self._duration_key = f"{duration_hours}h"
        self._attr_name = f"Best {duration_hours}h block"

    def _block(self) -> dict | None:
        return self.coordinator.data["best_blocks"].get(self._duration_key)

    @property
    def is_on(self) -> bool:
        block = self._block()
        return bool(block and block["starts_now"])

    @property
    def extra_state_attributes(self) -> dict:
        block = self._block()
        if block is None:
            # Not enough known blocks to fit this duration at all.
            return {"planned_start": None, "planned_end": None, "average_score": None}
        return {
            "planned_start": block["start"],
            "planned_end": block["end"],
            "average_score": block["average_score"],
        }


class SemsPauseBinarySensor(SemsBinarySensorBase):
    """ON during the worst blocks of the day — time to switch a device OFF.

    The counterpart of the best-block sensors. Those say "start now"; this
    one says "pause now", for the appliances where the win is skipping the
    expensive hours rather than picking the cheap ones: a freezer, a
    boiler, a circulation pump.

    The point of doing this in SEMS instead of a template is the spacing.
    Expensive hours cluster, so "the four worst hours of the day" is
    regularly one unbroken evening block — long enough for a freezer to
    thaw. SEMS picks the worst blocks it can while keeping every pause
    shorter than the limit you set, including across midnight.

    Stays OFF until you set "pause hours per day" in the options. The
    attributes always show the full plan, so you can also automate on the
    planned times instead of on this sensor flipping.
    """

    _attr_name = "Pause now"
    _attr_icon = "mdi:pause-octagon-outline"

    def __init__(self, coordinator: SemsCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry, "pause_now")

    @property
    def is_on(self) -> bool:
        return bool(self.coordinator.data["pause"]["now"])

    @property
    def extra_state_attributes(self) -> dict:
        plan = self.coordinator.data["pause"]
        return {
            "enabled": plan["enabled"],
            "hours_per_day": plan["hours_per_day"],
            "max_consecutive_hours": plan["max_consecutive_hours"],
            "next_pause": plan["next"],
            "pauses_today": plan["today"],
            "pauses_tomorrow": plan["tomorrow"],
        }
