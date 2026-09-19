"""JDECo sensor entities."""

from __future__ import annotations
import logging
from datetime import datetime
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import JDecoCoordinator
from .models import CoordinatorData

_LOGGER = logging.getLogger(__name__)


def _get_recharge_metrics(data: CoordinatorData | None) -> dict[str, Any]:
    """Calculate energy, financial, and rate breakdown from last recharge."""
    if not data or not data.agreement:
        return {}
    a = data.agreement
    chrg = a.lastPCChargeDetails
    lv = data.last_voucher

    payment_amt = (
        chrg.paymentAMT if chrg and chrg.paymentAMT is not None
        else (lv.paidAMT if lv else None)
    )
    cons_qty = (
        chrg.consQTY if chrg and chrg.consQTY is not None
        else (lv.consumptionQTY if lv else None)
    )
    cons_cost = (
        chrg.consCost if chrg and chrg.consCost is not None
        else (lv.consumptionPrice if lv else None)
    )
    vat = (
        chrg.VAT if chrg and chrg.VAT is not None
        else (lv.VAT if lv else None)
    )
    misc = (
        chrg.miscAMT if chrg and chrg.miscAMT is not None
        else (lv.totalMISC if lv else None)
    )

    clean_rate = round(cons_cost / cons_qty, 4) if cons_cost and cons_qty else None
    clean_kwh_per_nis = round(cons_qty / cons_cost, 4) if cons_cost and cons_qty else None
    effective_rate = round(payment_amt / cons_qty, 4) if payment_amt and cons_qty else None
    effective_kwh_per_nis = round(cons_qty / payment_amt, 4) if payment_amt and cons_qty else None
    overhead_pct = (
        round(((payment_amt - cons_cost) / payment_amt) * 100.0, 2)
        if payment_amt and cons_cost is not None
        else None
    )

    return {
        "payment_amt": payment_amt,
        "cons_qty": cons_qty,
        "cons_cost": cons_cost,
        "vat": vat,
        "misc": misc,
        "clean_rate": clean_rate,
        "clean_kwh_per_nis": clean_kwh_per_nis,
        "effective_rate": effective_rate,
        "effective_kwh_per_nis": effective_kwh_per_nis,
        "overhead_percent": overhead_pct,
    }


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinators: dict[str, JDecoCoordinator] = hass.data[DOMAIN][entry.entry_id]["coordinators"]

    entities: list[SensorEntity] = []
    for agree_no, coord in coordinators.items():
        entities.extend([
            JDecoPrepaidCreditSensor(coord, agree_no),
            JDecoCurrentReadingSensor(coord, agree_no),
            JDecoReadingTimeSensor(coord, agree_no),
            JDecoLastMeterReadingSensor(coord, agree_no),
            JDecoLastRechargeAmountSensor(coord, agree_no),
            JDecoLastRechargeKWhSensor(coord, agree_no),
            JDecoLastRechargePureCostSensor(coord, agree_no),
            JDecoLastRechargeVatSensor(coord, agree_no),
            JDecoLastRechargeFeesSensor(coord, agree_no),
            JDecoCleanKWhPerNISSensor(coord, agree_no),
            JDecoEffectiveKWhPerNISSensor(coord, agree_no),
            JDecoCleanTariffSensor(coord, agree_no),
            JDecoEffectiveTariffSensor(coord, agree_no),
            JDecoLastRechargeDateSensor(coord, agree_no),
            JDecoLastSTSTokenSensor(coord, agree_no),
            JDecoLastReceiptSensor(coord, agree_no),
            JDecoLastVoucherNoSensor(coord, agree_no),
            JDecoNextBillAmountSensor(coord, agree_no),
            JDecoDaysToNextRechargeSensor(coord, agree_no),
            JDecoGeneralAVGSensor(coord, agree_no),
            JDecoSummerAVGSensor(coord, agree_no),
            JDecoWinterAVGSensor(coord, agree_no),
            JDecoMonthlyKWhSensor(coord, agree_no),
            JDecoMonthlyCostSensor(coord, agree_no),
            JDecoYearlyKWhSensor(coord, agree_no),
            JDecoMeterCategorySensor(coord, agree_no),
            JDecoMeterNoSensor(coord, agree_no),
            JDecoAgreeNoSensor(coord, agree_no),
            JDecoLastUpdateSensor(coord, agree_no),
        ])

    async_add_entities(entities)


class JDecoSensor(CoordinatorEntity[CoordinatorData], SensorEntity):
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


class JDecoPrepaidCreditSensor(JDecoSensor):
    """Remaining credit / prepayment balance in kWh."""
    _attr_device_class = SensorDeviceClass.ENERGY
    _attr_native_unit_of_measurement = "kWh"
    _attr_suggested_display_precision = 2
    _attr_icon = "mdi:lightning-bolt-circle"

    def __init__(self, c, a):
        super().__init__(c, a, "remaining_credit", "Remaining Credit")

    @property
    def native_value(self):
        a = self.coordinator.data.agreement
        if a and a.smartMeterReading and a.smartMeterReading.prepaymentBalance is not None:
            return a.smartMeterReading.prepaymentBalance
        if a and a.totalBalance is not None:
            try:
                return float(a.totalBalance)
            except (ValueError, TypeError):
                pass
        return None


class JDecoCurrentReadingSensor(JDecoSensor):
    """Current live meter reading in kWh."""
    _attr_device_class = SensorDeviceClass.ENERGY
    _attr_state_class = SensorStateClass.TOTAL_INCREASING
    _attr_native_unit_of_measurement = "kWh"
    _attr_icon = "mdi:meter-electric"

    def __init__(self, c, a):
        super().__init__(c, a, "current_reading", "Current Meter Reading")

    @property
    def native_value(self):
        a = self.coordinator.data.agreement
        if a and a.smartMeterReading and a.smartMeterReading.currentReadingKW is not None:
            return a.smartMeterReading.currentReadingKW
        return None


class JDecoReadingTimeSensor(JDecoSensor):
    """Timestamp of the meter reading."""
    _attr_device_class = SensorDeviceClass.TIMESTAMP
    _attr_icon = "mdi:clock-outline"

    def __init__(self, c, a):
        super().__init__(c, a, "meter_reading_time", "Meter Reading Time")

    @property
    def native_value(self):
        a = self.coordinator.data.agreement
        if a and a.smartMeterReading:
            return a.smartMeterReading.readingDateTime_dt
        return None


class JDecoLastMeterReadingSensor(JDecoSensor):
    """Last recorded meter reading."""
    _attr_device_class = SensorDeviceClass.ENERGY
    _attr_native_unit_of_measurement = "kWh"
    _attr_icon = "mdi:counter"

    def __init__(self, c, a):
        super().__init__(c, a, "last_meter_reading", "Last Recorded Reading")

    @property
    def native_value(self):
        a = self.coordinator.data.agreement
        return a.lastMeterReading if a else None


class JDecoLastRechargeAmountSensor(JDecoSensor):
    """Last recharge payment amount."""
    _attr_device_class = SensorDeviceClass.MONETARY
    _attr_state_class = SensorStateClass.TOTAL
    _attr_native_unit_of_measurement = "ILS"
    _attr_suggested_display_precision = 2
    _attr_icon = "mdi:cash-plus"

    def __init__(self, c, a):
        super().__init__(c, a, "last_recharge_amount", "Last Recharge Amount")

    @property
    def native_value(self):
        m = _get_recharge_metrics(self.coordinator.data)
        return m.get("payment_amt")

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        m = _get_recharge_metrics(self.coordinator.data)
        attrs = {}
        if m.get("cons_cost") is not None:
            attrs["pure_electricity_cost_ils"] = m["cons_cost"]
        if m.get("vat") is not None:
            attrs["vat_amount_ils"] = m["vat"]
        if m.get("misc") is not None:
            attrs["misc_service_fees_ils"] = m["misc"]
        if m.get("clean_rate") is not None:
            attrs["clean_tariff_ils_per_kwh"] = m["clean_rate"]
        if m.get("clean_kwh_per_nis") is not None:
            attrs["clean_kwh_per_ils"] = m["clean_kwh_per_nis"]
        if m.get("effective_rate") is not None:
            attrs["effective_tariff_ils_per_kwh"] = m["effective_rate"]
        if m.get("effective_kwh_per_nis") is not None:
            attrs["effective_kwh_per_ils"] = m["effective_kwh_per_nis"]
        if m.get("overhead_percent") is not None:
            attrs["overhead_percent"] = m["overhead_percent"]
        return attrs


class JDecoLastRechargePureCostSensor(JDecoSensor):
    """Last recharge pure electricity cost before fees and VAT."""
    _attr_device_class = SensorDeviceClass.MONETARY
    _attr_state_class = SensorStateClass.TOTAL
    _attr_native_unit_of_measurement = "ILS"
    _attr_suggested_display_precision = 2
    _attr_icon = "mdi:cash-check"

    def __init__(self, c, a):
        super().__init__(c, a, "last_recharge_pure_cost", "Last Recharge Pure Electricity Cost")

    @property
    def native_value(self):
        m = _get_recharge_metrics(self.coordinator.data)
        return m.get("cons_cost")


class JDecoLastRechargeVatSensor(JDecoSensor):
    """Last recharge VAT amount."""
    _attr_device_class = SensorDeviceClass.MONETARY
    _attr_state_class = SensorStateClass.TOTAL
    _attr_native_unit_of_measurement = "ILS"
    _attr_suggested_display_precision = 2
    _attr_icon = "mdi:cash-minus"

    def __init__(self, c, a):
        super().__init__(c, a, "last_recharge_vat", "Last Recharge VAT")

    @property
    def native_value(self):
        m = _get_recharge_metrics(self.coordinator.data)
        return m.get("vat")


class JDecoLastRechargeFeesSensor(JDecoSensor):
    """Last recharge service and miscellaneous fees."""
    _attr_device_class = SensorDeviceClass.MONETARY
    _attr_state_class = SensorStateClass.TOTAL
    _attr_native_unit_of_measurement = "ILS"
    _attr_suggested_display_precision = 2
    _attr_icon = "mdi:receipt-outline"

    def __init__(self, c, a):
        super().__init__(c, a, "last_recharge_fees", "Last Recharge Service Fees")

    @property
    def native_value(self):
        m = _get_recharge_metrics(self.coordinator.data)
        return m.get("misc")


class JDecoCleanKWhPerNISSensor(JDecoSensor):
    """Clean energy rate: kWh bought per 1 NIS of pure electricity."""
    _attr_native_unit_of_measurement = "kWh/ILS"
    _attr_suggested_display_precision = 3
    _attr_icon = "mdi:scale-balance"

    def __init__(self, c, a):
        super().__init__(c, a, "clean_kwh_per_nis", "Clean Energy Rate (kWh / NIS)")

    @property
    def native_value(self):
        m = _get_recharge_metrics(self.coordinator.data)
        return m.get("clean_kwh_per_nis")


class JDecoEffectiveKWhPerNISSensor(JDecoSensor):
    """Effective energy rate: kWh bought per 1 NIS paid (all-in)."""
    _attr_native_unit_of_measurement = "kWh/ILS"
    _attr_suggested_display_precision = 3
    _attr_icon = "mdi:calculator-variant-outline"

    def __init__(self, c, a):
        super().__init__(c, a, "effective_kwh_per_nis", "Effective Energy Rate (kWh / NIS)")

    @property
    def native_value(self):
        m = _get_recharge_metrics(self.coordinator.data)
        return m.get("effective_kwh_per_nis")


class JDecoCleanTariffSensor(JDecoSensor):
    """Clean electricity tariff (pure cost per kWh)."""
    _attr_native_unit_of_measurement = "ILS/kWh"
    _attr_suggested_display_precision = 3
    _attr_icon = "mdi:tag-outline"

    def __init__(self, c, a):
        super().__init__(c, a, "clean_tariff", "Clean Electricity Tariff")

    @property
    def native_value(self):
        m = _get_recharge_metrics(self.coordinator.data)
        return m.get("clean_rate")


class JDecoEffectiveTariffSensor(JDecoSensor):
    """Effective electricity tariff (all-in cost per kWh paid)."""
    _attr_native_unit_of_measurement = "ILS/kWh"
    _attr_suggested_display_precision = 3
    _attr_icon = "mdi:tag-text-outline"

    def __init__(self, c, a):
        super().__init__(c, a, "effective_tariff", "Effective Electricity Tariff")

    @property
    def native_value(self):
        m = _get_recharge_metrics(self.coordinator.data)
        return m.get("effective_rate")


class JDecoLastRechargeKWhSensor(JDecoSensor):
    """Energy amount in kWh from the last recharge."""
    _attr_device_class = SensorDeviceClass.ENERGY
    _attr_native_unit_of_measurement = "kWh"
    _attr_icon = "mdi:lightning-bolt"

    def __init__(self, c, a):
        super().__init__(c, a, "last_recharge_kwh", "Last Recharge Energy")

    @property
    def native_value(self):
        a = self.coordinator.data.agreement
        if a and a.lastPCChargeDetails and a.lastPCChargeDetails.consQTY is not None:
            return a.lastPCChargeDetails.consQTY
        lv = self.coordinator.data.last_voucher
        if lv and lv.consumptionQTY is not None:
            return lv.consumptionQTY
        return None


class JDecoLastRechargeDateSensor(JDecoSensor):
    """Date of the last recharge."""
    _attr_device_class = SensorDeviceClass.TIMESTAMP
    _attr_icon = "mdi:calendar-check"

    def __init__(self, c, a):
        super().__init__(c, a, "last_recharge_date", "Last Recharge Date")

    @property
    def native_value(self):
        a = self.coordinator.data.agreement
        if a and a.lastPCChargeDetails and a.lastPCChargeDetails.paymentDate_dt:
            return a.lastPCChargeDetails.paymentDate_dt
        lv = self.coordinator.data.last_voucher
        if lv and lv.voucherDate_dt:
            return lv.voucherDate_dt
        return None


class JDecoLastSTSTokenSensor(JDecoSensor):
    """Last STS Token code."""
    _attr_icon = "mdi:numeric"

    def __init__(self, c, a):
        super().__init__(c, a, "last_sts_token", "Last STS Token")

    @property
    def native_value(self):
        a = self.coordinator.data.agreement
        if a and a.lastPCChargeDetails and a.lastPCChargeDetails.STSToken:
            return a.lastPCChargeDetails.STSToken
        lv = self.coordinator.data.last_voucher
        if lv and lv.STSToken:
            return lv.STSToken
        return None


class JDecoLastReceiptSensor(JDecoSensor):
    """Receipt number of last charge."""
    _attr_icon = "mdi:receipt"

    def __init__(self, c, a):
        super().__init__(c, a, "last_recharge_receipt", "Last Recharge Receipt")

    @property
    def native_value(self):
        a = self.coordinator.data.agreement
        if a and a.lastPCChargeDetails:
            return a.lastPCChargeDetails.receiptNo
        return None


class JDecoLastVoucherNoSensor(JDecoSensor):
    """Last voucher number."""
    _attr_icon = "mdi:receipt-text"

    def __init__(self, c, a):
        super().__init__(c, a, "last_voucher_number", "Last Voucher Number")

    @property
    def native_value(self):
        lv = self.coordinator.data.last_voucher
        return lv.voucherNo if lv else None


class JDecoNextBillAmountSensor(JDecoSensor):
    """Estimated amount for next recharge."""
    _attr_device_class = SensorDeviceClass.MONETARY
    _attr_native_unit_of_measurement = "ILS"
    _attr_icon = "mdi:currency-ils"

    def __init__(self, c, a):
        super().__init__(c, a, "estimated_next_recharge", "Estimated Next Recharge Amount")

    @property
    def native_value(self):
        a = self.coordinator.data.agreement
        return a.estimatedNextVoucherAMT if a else None


class JDecoDaysToNextRechargeSensor(JDecoSensor):
    """Estimated days until next recharge is needed."""
    _attr_native_unit_of_measurement = "d"
    _attr_icon = "mdi:calendar-clock"

    def __init__(self, c, a):
        super().__init__(c, a, "estimated_days_to_recharge", "Estimated Days to Next Recharge")

    @property
    def native_value(self):
        a = self.coordinator.data.agreement
        return a.estimatedDaysForNextVoucher if a else None


class JDecoGeneralAVGSensor(JDecoSensor):
    """General monthly average consumption in kWh."""
    _attr_device_class = SensorDeviceClass.ENERGY
    _attr_native_unit_of_measurement = "kWh"
    _attr_icon = "mdi:chart-bell-curve"

    def __init__(self, c, a):
        super().__init__(c, a, "meter_general_avg", "Monthly Average Consumption")

    @property
    def native_value(self):
        a = self.coordinator.data.agreement
        return a.meterGeneralAVG if a else None


class JDecoSummerAVGSensor(JDecoSensor):
    """Summer average consumption in kWh."""
    _attr_device_class = SensorDeviceClass.ENERGY
    _attr_native_unit_of_measurement = "kWh"
    _attr_icon = "mdi:weather-sunny"

    def __init__(self, c, a):
        super().__init__(c, a, "meter_summer_avg", "Summer Average Consumption")

    @property
    def native_value(self):
        a = self.coordinator.data.agreement
        return a.meterSummerAVG if a else None


class JDecoWinterAVGSensor(JDecoSensor):
    """Winter average consumption in kWh."""
    _attr_device_class = SensorDeviceClass.ENERGY
    _attr_native_unit_of_measurement = "kWh"
    _attr_icon = "mdi:snowflake"

    def __init__(self, c, a):
        super().__init__(c, a, "meter_winter_avg", "Winter Average Consumption")

    @property
    def native_value(self):
        a = self.coordinator.data.agreement
        return a.meterWinterAVG if a else None


class JDecoMonthlyKWhSensor(JDecoSensor):
    """Current month consumption in kWh."""
    _attr_device_class = SensorDeviceClass.ENERGY
    _attr_state_class = SensorStateClass.TOTAL_INCREASING
    _attr_native_unit_of_measurement = "kWh"
    _attr_icon = "mdi:calendar-month"

    def __init__(self, c, a):
        super().__init__(c, a, "monthly_kwh", "Monthly Consumption")

    @property
    def native_value(self):
        return self.coordinator.data.monthly_kwh


class JDecoMonthlyCostSensor(JDecoSensor):
    """Current month cost in ILS."""
    _attr_device_class = SensorDeviceClass.MONETARY
    _attr_state_class = SensorStateClass.TOTAL
    _attr_native_unit_of_measurement = "ILS"
    _attr_icon = "mdi:cash-multiple"

    def __init__(self, c, a):
        super().__init__(c, a, "monthly_cost", "Monthly Cost")

    @property
    def native_value(self):
        return self.coordinator.data.monthly_cost


class JDecoYearlyKWhSensor(JDecoSensor):
    """Current year consumption in kWh."""
    _attr_device_class = SensorDeviceClass.ENERGY
    _attr_state_class = SensorStateClass.TOTAL_INCREASING
    _attr_native_unit_of_measurement = "kWh"
    _attr_icon = "mdi:calendar-star"

    def __init__(self, c, a):
        super().__init__(c, a, "yearly_kwh", "Yearly Consumption")

    @property
    def native_value(self):
        return self.coordinator.data.yearly_kwh


class JDecoMeterCategorySensor(JDecoSensor):
    """Meter Category description."""
    _attr_icon = "mdi:information-outline"

    def __init__(self, c, a):
        super().__init__(c, a, "meter_category", "Meter Category")

    @property
    def native_value(self):
        a = self.coordinator.data.agreement
        return a.categoryDescE or a.categoryDescA if a else None


class JDecoMeterNoSensor(JDecoSensor):
    """Meter Serial Number."""
    _attr_icon = "mdi:identifier"

    def __init__(self, c, a):
        super().__init__(c, a, "meter_number", "Meter Number")

    @property
    def native_value(self):
        a = self.coordinator.data.agreement
        return a.meterNo if a else None


class JDecoAgreeNoSensor(JDecoSensor):
    """Agreement Number."""
    _attr_icon = "mdi:file-document-outline"

    def __init__(self, c, a):
        super().__init__(c, a, "agreement_number", "Agreement Number")

    @property
    def native_value(self):
        a = self.coordinator.data.agreement
        return a.agreeNo if a else None


class JDecoLastUpdateSensor(JDecoSensor):
    """Timestamp of last data update."""
    _attr_device_class = SensorDeviceClass.TIMESTAMP
    _attr_icon = "mdi:update"

    def __init__(self, c, a):
        super().__init__(c, a, "last_update", "Last Updated")

    @property
    def native_value(self):
        return self.coordinator.data.last_update
