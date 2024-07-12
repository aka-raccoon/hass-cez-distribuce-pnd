"""CEZ Distribuce PND sensor platform."""

import logging
from dataclasses import dataclass
from datetime import UTC, timedelta
from functools import partial

from cez_distribuce_data_fetcher import get_energy_measurements
from homeassistant.components import recorder
from homeassistant.components.recorder.models.statistics import (
    StatisticData,
    StatisticMetaData,
)
from homeassistant.components.recorder.statistics import (
    async_import_statistics,
    get_last_statistics,
    statistic_during_period,
)
from homeassistant.components.sensor import SensorEntity, SensorEntityDescription
from homeassistant.components.sensor.const import SensorDeviceClass, SensorStateClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_DEVICE, UnitOfEnergy
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.update_coordinator import (
    CoordinatorEntity,
    DataUpdateCoordinator,
)
from homeassistant.util.dt import async_get_time_zone, now

from .const import DOMAIN

_LOGGER = logging.getLogger(name=__name__)


@dataclass(kw_only=True, frozen=True)
class CezDistribucePndEntityDescription(SensorEntityDescription):
    """Describes CEZ distribuce PND sensor entity."""


CONSUMED_ENERGY = "consumed_energy"
RETURNED_ENERGY = "returned_energy"

SENSORS: tuple[CezDistribucePndEntityDescription, ...] = (
    CezDistribucePndEntityDescription(
        key=CONSUMED_ENERGY,
        icon="mdi:transmission-tower-export",
    ),
    CezDistribucePndEntityDescription(
        key=RETURNED_ENERGY,
        icon="mdi:transmission-tower-import",
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities,
) -> None:
    config = hass.data[DOMAIN][config_entry.entry_id]
    coordinator = CezDistribucePndCoordinator(hass=hass, config=config)
    await coordinator.async_config_entry_first_refresh()
    async_add_entities(
        (
            CezDistribucePndSensor(
                coordinator=coordinator, device=config[CONF_DEVICE], description=sensor
            )
            for sensor in SENSORS
        ),
        update_before_add=True,
    )


OFFSET = 13


class CezDistribucePndCoordinator(DataUpdateCoordinator):
    def __init__(self, hass: HomeAssistant, config: dict[str, str]) -> None:
        super().__init__(
            hass=hass,
            logger=_LOGGER,
            name=DOMAIN,
            update_interval=timedelta(hours=1),
        )
        self.username = config["username"]
        self.password = config["password"]
        self.device = config["device"]
        self.selenium_driver = config["selenium driver"]
        self.selenium_url = config["selenium url"]
        self.selenium_remote = config["selenium remote"]

    async def _async_update_data(self) -> dict:
        time_zone = await async_get_time_zone(self.hass.config.time_zone)
        from_time = now().astimezone(tz=time_zone) - timedelta(hours=OFFSET)
        from_time = from_time.replace(minute=0, second=0, microsecond=0)
        to_time = from_time + timedelta(hours=1)
        get_measurement = partial(
            get_energy_measurements,
            from_time=from_time,
            pnd_device=self.device,
            pnd_password=self.password,
            pnd_user=self.username,
            to_time=to_time,
            remote_connection=self.selenium_remote,
            selenium_driver=self.selenium_driver,
            selenium_url=self.selenium_url,
        )
        measurements = await self.hass.async_add_executor_job(get_measurement)
        from_grid_measurements = []
        to_grid_measurements = []
        for _date, from_grid, to_grid in measurements:
            from_grid_measurements.append(from_grid)
            to_grid_measurements.append(to_grid)
        total_from_grid_kwh = sum(kw * 0.25 for kw in from_grid_measurements)
        total_to_grid_kwh = sum(kw * 0.25 for kw in to_grid_measurements)

        return {
            CONSUMED_ENERGY: total_from_grid_kwh,
            RETURNED_ENERGY: total_to_grid_kwh,
            "from": from_time,
            "to": to_time,
        }


class CezDistribucePndSensor(CoordinatorEntity, SensorEntity):
    """Representation of a CEZ Distribuce PND sensor."""

    _attr_native_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR
    _attr_device_class = SensorDeviceClass.ENERGY
    _attr_state_class = SensorStateClass.TOTAL

    def __init__(
        self, coordinator, device: str, description: SensorEntityDescription
    ) -> None:
        super().__init__(coordinator=coordinator)
        self._device = device.lower().replace(" ", "_")
        self._attr_available = True
        self.description = description
        self._attr_unique_id = f"{self._device}_{self.description.key}"
        self.sensor_name = f"sensor.cez_distribuce_pnd_{self._attr_unique_id}"

    @callback
    def _handle_coordinator_update(self) -> None:
        """Update the sensor."""
        self.async_schedule_update_ha_state(force_refresh=True)

    async def async_update(self) -> None:
        start = self.coordinator.data["from"]
        to_time = self.coordinator.data["to"]
        available_stats = await recorder.get_instance(self.hass).async_add_executor_job(
            statistic_during_period,
            self.hass,
            start.astimezone(tz=UTC),
            to_time.astimezone(tz=UTC),
            self.sensor_name,
            None,
            {"change"},
        )
        change = available_stats.get("change", 0)
        if change:
            return
        last_stats = await recorder.get_instance(self.hass).async_add_executor_job(
            get_last_statistics,
            self.hass,
            1,
            self.sensor_name,
            False,
            {"sum"},
        )
        energy_sum = last_stats.get(self.sensor_name, [{"sum": 0}])[0].get("sum", 0)
        state = self.coordinator.data[self.description.key]
        metadata = StatisticMetaData(
            has_mean=False,
            has_sum=True,
            unit_of_measurement="kWh",
            name=None,
            source="recorder",
            statistic_id=self.sensor_name,
        )
        statistics = StatisticData(start=start, state=state, sum=energy_sum + state)
        async_import_statistics(
            hass=self.hass,
            metadata=metadata,
            statistics=[statistics],
        )
