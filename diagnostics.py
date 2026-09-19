"""JDECo diagnostics platform — exposes debug info with secrets redacted."""

from __future__ import annotations
from typing import Any
from homeassistant.components.diagnostics import async_redact_data
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import DOMAIN

# Fields that must NEVER appear in diagnostic output
TO_REDACT = {
    "password", "session_key", "authKey", "STSToken",
    "DEVID", "GID", "FRF", "mobileNo", "registeredEmail",
    "gid", "devid",
}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
) -> dict[str, Any]:
    entry_data = hass.data[DOMAIN].get(entry.entry_id, {})
    coord = entry_data.get("coordinator")
    data = coord.data if coord else None

    agree = data.agreement if data else None
    kwqty = data.kwqty if data else None
    debt  = data.debt if data else None
    voucher = data.last_voucher if data else None

    return {
        "config_entry": async_redact_data(dict(entry.data), TO_REDACT),
        "session": {
            "authenticated": entry_data.get("client", None) and
                             entry_data["client"].is_authenticated,
        },
        "last_update": str(data.last_update) if data else None,
        "agreement": {
            "agree_no": agree.agreeNo if agree else None,
            "meter_no": agree.meterNo if agree else None,
            "is_prepaid": agree.isPrepaidMeter if agree else None,
            "is_smart": agree.isSmartMeter if agree else None,
            "can_charge_remotely": agree.canChargeRemotely if agree else None,
            "days_to_bill": agree.estimatedDaysForNextVoucher if agree else None,
            "total_balance": agree.totalBalance if agree else None,
            "last_meter_reading": agree.lastMeterReading if agree else None,
        },
        "smart_meter": {
            "current_kwh": agree.smartMeterReading.currentReadingKW if agree and agree.smartMeterReading else None,
            "prepay_balance": agree.smartMeterReading.prepaymentBalance if agree and agree.smartMeterReading else None,
            "reading_time": agree.smartMeterReading.readingDateTime if agree and agree.smartMeterReading else None,
            "is_estimated": agree.smartMeterReading.readingType == "2" if agree and agree.smartMeterReading else None,
        },
        "kwqty": {
            "result_code": kwqty.result_code if kwqty else None,
            "credit_ils": kwqty.payment_amt if kwqty else None,
            "credit_kwh": kwqty.cons_qty if kwqty else None,
        },
        "debt": {
            "result_code": debt.result_code if debt else None,
            "debt_ils": debt.debt_value if debt else None,
            "unpaid_vouchers": debt.no_of_vouchers if debt else None,
        },
        "last_voucher": {
            "voucher_no": voucher.voucherNo if voucher else None,
            "voucher_date": voucher.voucherDate if voucher else None,
            "amount_ils": voucher.voucherAMT if voucher else None,
            "consumption_kwh": voucher.consumptionQTY if voucher else None,
        },
        "consumption_derived": {
            "monthly_kwh": data.monthly_kwh if data else None,
            "monthly_cost": data.monthly_cost if data else None,
            "yearly_kwh": data.yearly_kwh if data else None,
        },
    }
