"""JDECo binary sensor entities."""

from __future__ import annotations
from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass, BinarySensorEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import JDecoCoordinator
from .models import CoordinatorData


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinators: dict[str, JDecoCoordinator] = hass.data[DOMAIN][entry.entry_id]["coordinators"]
    entities: list[BinarySensorEntity] = []
    for agree_no, coord in coordinators.items():
        entities.extend([
            JDecoIsPrepaidSensor(coord, agree_no),
            JDecoIsSmartSensor(coord, agree_no),
            JDecoCanChargeRemotelySensor(coord, agree_no),
            JDecoEstimatedReadingSensor(coord, agree_no),
            JDecoLowCreditSensor(coord, agree_no),
        ])
    async_add_entities(entities)


class JDecoBinarySensor(CoordinatorEntity[CoordinatorData], BinarySensorEntity):
    _attr_has_entity_name = True

    def __init__(self, coordinator: JDecoCoordinator, agree_no: str, key: str, name: str):
        super().__init__(coordinator)
        self._agree_no = agree_no
        self._attr_unique_id = f"jdeco_{agree_no}_{key}"
        self._attr_name = name
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, agree_no)},
            name=f"JDECo Meter {agree_no}",
            manufacturer="Jerusalem District Electricity Co.",
            model="JDECo Account",
            configuration_url="https://www.jdeco.net",
        )

    @property
    def available(self) -> bool:
        return (
            super().available
            and self.coordinator.data is not None
            and self.coordinator.data.agreement is not None
        )


class JDecoIsPrepaidSensor(JDecoBinarySensor):
    _attr_icon = "mdi:credit-card"

    def __init__(self, c, a): super().__init__(c, a, "is_prepaid", "Prepaid Meter")

    @property
    def is_on(self): return bool(self.coordinator.data.agreement.isPrepaidMeter)


class JDecoIsSmartSensor(JDecoBinarySensor):
    _attr_icon = "mdi:meter-electric"

    def __init__(self, c, a): super().__init__(c, a, "is_smart", "Smart Meter")

    @property
    def is_on(self): return bool(self.coordinator.data.agreement.isSmartMeter)


class JDecoCanChargeRemotelySensor(JDecoBinarySensor):
    _attr_icon = "mdi:remote"

    def __init__(self, c, a): super().__init__(c, a, "can_charge_remotely", "Remote Charging")

    @property
    def is_on(self): return bool(self.coordinator.data.agreement.canChargeRemotely)


class JDecoEstimatedReadingSensor(JDecoBinarySensor):
    _attr_device_class = BinarySensorDeviceClass.PROBLEM
    _attr_icon = "mdi:alert-circle"

    def __init__(self, c, a): super().__init__(c, a, "estimated_reading", "Estimated Reading")

    @property
    def available(self) -> bool:
        a = self.coordinator.data.agreement if self.coordinator.data else None
        return super().available and a is not None and bool(a.isSmartMeter) and a.smartMeterReading is not None

    @property
    def is_on(self):
        smr = self.coordinator.data.agreement.smartMeterReading
        return smr is not None and smr.readingType == "2"


class JDecoLowCreditSensor(JDecoBinarySensor):
    _attr_device_class = BinarySensorDeviceClass.PROBLEM
    _attr_icon = "mdi:battery-alert"

    def __init__(self, c, a): super().__init__(c, a, "low_credit", "Low Credit Warning")

    @property
    def is_on(self):
        a = self.coordinator.data.agreement
        if not a:
            return False
        # Alert if estimated days < 5
        if a.estimatedDaysForNextVoucher is not None and a.estimatedDaysForNextVoucher < 5:
            return True
        # Alert if prepaid credit < 50 ILS
        if a.smartMeterReading and a.smartMeterReading.prepaymentBalance is not None:
            if a.smartMeterReading.prepaymentBalance < 50.0:
                return True
        return False
