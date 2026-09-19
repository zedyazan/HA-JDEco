"""JDECo button entities for on-demand actions."""

from __future__ import annotations
import logging

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import JDecoCoordinator
from .models import CoordinatorData

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinators: dict[str, JDecoCoordinator] = hass.data[DOMAIN][entry.entry_id]["coordinators"]
    entities: list[ButtonEntity] = []
    for agree_no, coord in coordinators.items():
        entities.append(JDecoCheckCreditButton(coord, agree_no))
    async_add_entities(entities)


class JDecoCheckCreditButton(CoordinatorEntity[CoordinatorData], ButtonEntity):
    """Button to trigger an immediate live credit / balance check."""

    _attr_has_entity_name = True
    _attr_icon = "mdi:cash-sync"

    def __init__(self, coordinator: JDecoCoordinator, agree_no: str):
        super().__init__(coordinator)
        self._agree_no = agree_no
        self._attr_unique_id = f"jdeco_{agree_no}_check_credit"
        self._attr_name = "Check Credit"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, agree_no)},
            name=f"JDECo Meter {agree_no}",
            manufacturer="Jerusalem District Electricity Co.",
            model="JDECo Account",
            configuration_url="https://www.jdeco.net",
        )

    async def async_press(self) -> None:
        """Handle the button press."""
        _LOGGER.info("Check Credit button pressed for agreement %s — requesting live update", self._agree_no)
        await self.coordinator.async_request_refresh()
