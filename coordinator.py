"""
JDECo DataUpdateCoordinator.
"""

from __future__ import annotations

import logging
import asyncio
from collections import defaultdict
from datetime import datetime, timedelta

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .client import JDecoClient, AuthError, CannotConnect, ProtocolError
from .const import DOMAIN, RESULT_NO_DATA
from .models import (
    AgreementDetails, BillFinancialParams, ChargeDetails,
    CoordinatorData, DebtData, KWQtyData, MeterReading,
    TariffClass, VoucherClass, parse_wcf_date,
)

_LOGGER = logging.getLogger(__name__)


class JDecoCoordinator(DataUpdateCoordinator[CoordinatorData]):

    def __init__(self, hass: HomeAssistant, client: JDecoClient, agree_no: str, interval_minutes: int):
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN}_{agree_no}",
            update_interval=timedelta(minutes=interval_minutes),
        )
        self.client = client
        self.agree_no = agree_no
        self._consecutive_failures: int = 0

    async def _async_update_data(self) -> CoordinatorData:
        data = CoordinatorData(last_update=dt_util.now())

        # ── Primary snapshot (contains all agreement, meter, balance, recharge, vouchers) ──
        raw = None
        for attempt in range(2):
            try:
                raw = await self.client.async_get_agreement(self.agree_no)
                break
            except AuthError as err:
                if attempt == 0:
                    _LOGGER.info("Auth error during update (%s) — re-authenticating and retrying...", err)
                    try:
                        await self.client.async_login()
                        continue
                    except Exception as login_err:
                        _LOGGER.warning("Re-authentication failed: %s", login_err)
                _LOGGER.error("JDECo authentication failed for %s: %s", self.agree_no, err)
                if self.data and self.data.agreement and self._consecutive_failures < 3:
                    self._consecutive_failures += 1
                    _LOGGER.warning("Retaining previous meter data on auth failure (%d/3)", self._consecutive_failures)
                    return self.data
                self._consecutive_failures += 1
                raise UpdateFailed(f"Authentication error: {err}") from err
            except (CannotConnect, ProtocolError) as err:
                if attempt == 0:
                    _LOGGER.debug("Connection glitch during update (%s) — retrying in 3s...", err)
                    await asyncio.sleep(3.0)
                    continue
                _LOGGER.warning("JDECo fetch failed for %s: %s", self.agree_no, err)
                if self.data and self.data.agreement and self._consecutive_failures < 3:
                    self._consecutive_failures += 1
                    _LOGGER.warning("Retaining previous meter data on connection failure (%d/3)", self._consecutive_failures)
                    return self.data
                self._consecutive_failures += 1
                raise UpdateFailed(f"JDECo fetch failed: {err}") from err
            except Exception as err:
                _LOGGER.exception("Unexpected error fetching JDECo data: %s", err)
                if self.data and self.data.agreement and self._consecutive_failures < 3:
                    self._consecutive_failures += 1
                    return self.data
                self._consecutive_failures += 1
                raise UpdateFailed(f"Unexpected error: {err}") from err

        self._consecutive_failures = 0
        data.agreement = _parse_agreement(raw)

        # ── Derived: last voucher + monthly/yearly totals from paidVouchers ──
        if data.agreement and data.agreement.paidVouchers:
            data.last_voucher = data.agreement.paidVouchers[0]
            data.monthly_kwh, data.monthly_cost = _current_month_totals(
                data.agreement.paidVouchers
            )
            data.yearly_kwh = _current_year_total(data.agreement.paidVouchers)

        return data


def _parse_agreement(raw: dict) -> AgreementDetails:
    a = raw.get("agreement") or raw
    smr_raw = a.get("smartMeterReading")
    smr = None
    if smr_raw:
        cur_kw = smr_raw.get("currentReadingKW")
        try:
            cur_kw_flt = float(cur_kw) if cur_kw is not None else None
        except (ValueError, TypeError):
            cur_kw_flt = None

        bal = smr_raw.get("prepaymentBalance")
        try:
            bal_flt = float(bal) if bal is not None else None
        except (ValueError, TypeError):
            bal_flt = None

        smr = MeterReading(
            currentReadingKW=cur_kw_flt,
            prepaymentBalance=bal_flt,
            readingDateTime=smr_raw.get("readingDateTime"),
            readingDateTime_dt=parse_wcf_date(smr_raw.get("readingDateTime")),
            readingType=smr_raw.get("readingType"),
        )
    chrg_raw = a.get("lastPCChargeDetails")
    chrg = None
    if chrg_raw:
        chrg = ChargeDetails(
            paymentAMT=chrg_raw.get("paymentAMT"),
            consQTY=chrg_raw.get("consQTY"),
            paymentDate=chrg_raw.get("paymentDate"),
            paymentDate_dt=parse_wcf_date(chrg_raw.get("paymentDate")),
            receiptNo=chrg_raw.get("receiptNo"),
            STSToken=chrg_raw.get("STSToken"),
            debtAMT=chrg_raw.get("debtAMT"),
            fixedAMT=chrg_raw.get("fixedAMT"),
            VAT=chrg_raw.get("VAT"),
            consCost=chrg_raw.get("consCost"),
            miscAMT=chrg_raw.get("miscAMT"),
            deductionAMT=chrg_raw.get("deductionAMT"),
            interestAMT=chrg_raw.get("interestAMT"),
        )
    t_raw = a.get("tarrif")
    tariff = None
    if t_raw:
        tariff = TariffClass(
            tarrifNo=t_raw.get("tarrifNo"),
            tarrifNameE=t_raw.get("tarrifNameE"),
            cost=t_raw.get("cost"),
        )
    paid = [_parse_voucher(v) for v in (a.get("paidVouchers") or [])]
    return AgreementDetails(
        agreeNo=str(a.get("agreeNo") or ""),
        meterNo=str(a.get("meterNo") or ""),
        agreementNick=a.get("agreementNick"),
        usageType=a.get("usageType"),
        addressEng=a.get("addressEng"),
        FName=a.get("FName"),
        LName=a.get("LName"),
        isPrepaidMeter=a.get("isPrepaidMeter"),
        isSmartMeter=a.get("isSmartMeter"),
        canChargeRemotely=a.get("canChargeRemotely"),
        lastMeterReading=a.get("lastMeterReading"),
        lastMeterReadingDate=a.get("lastMeterReadingDate"),
        lastMeterReadingDate_dt=parse_wcf_date(a.get("lastMeterReadingDate")),
        totalBalance=a.get("totalBalance"),
        categoryDescA=a.get("categoryDescA"),
        categoryDescE=a.get("categoryDescE"),
        meterTypeA=a.get("meterTypeA"),
        meterTypeE=a.get("meterTypeE"),
        meterGeneralAVG=a.get("meterGeneralAVG"),
        meterSummerAVG=a.get("meterSummerAVG"),
        meterWinterAVG=a.get("meterWinterAVG"),
        estimatedDaysForNextVoucher=a.get("estimatedDaysForNextVoucher"),
        estimatedNextVoucherAMT=a.get("estimatedNextVoucherAMT"),
        nextEstimatedChargeDate=a.get("nextEstimatedChargeDate"),
        nextExpectedVoucherDate=a.get("nextExpectedVoucherDate"),
        smartMeterReading=smr,
        lastPCChargeDetails=chrg,
        tarrif=tariff,
        paidVouchers=paid,
    )


def _parse_voucher(raw: dict) -> VoucherClass:
    return VoucherClass(
        voucherNo=str(raw.get("voucherNo") or ""),
        voucherDate=raw.get("voucherDate"),
        voucherDate_dt=parse_wcf_date(raw.get("voucherDate")),
        voucherAMT=raw.get("voucherAMT"),
        paidAMT=raw.get("paidAMT"),
        remainAMT=raw.get("remainAMT"),
        netAMT=raw.get("netAMT"),
        consumptionQTY=raw.get("consumptionQTY"),
        consumptionPrice=raw.get("consumptionPrice"),
        currentReadingKW=raw.get("currentReadingKW"),
        previousReading=raw.get("previousReading"),
        readingDate=raw.get("readingDate"),
        readingDate_dt=parse_wcf_date(raw.get("readingDate")),
        lastDueDate=raw.get("lastDueDate"),
        lastDueDate_dt=parse_wcf_date(raw.get("lastDueDate")),
        fixedAMT=raw.get("fixedAMT"),
        VAT=raw.get("VAT"),
        INTAMT=raw.get("INTAMT"),
        totalMISC=raw.get("totalMISC"),
        readingType=raw.get("readingType"),
        STSToken=raw.get("STSToken"),
    )


def _parse_kwqty(raw: dict) -> KWQtyData:
    bp = raw.get("billParameters") or {}
    return KWQtyData(
        result_code=raw.get("resultCode", -1),
        payment_amt=bp.get("paymentAMT"),
        cons_qty=bp.get("consQTY"),
    )


def _parse_debt(raw: dict) -> DebtData:
    debt_obj = raw.get("debt") or {}
    raw_value = debt_obj.get("value")
    debt_value = None
    if raw_value is not None:
        try:
            debt_value = float(str(raw_value))
        except (ValueError, TypeError):
            pass
    return DebtData(
        result_code=raw.get("resultCode", -1),
        debt_value=debt_value,
        no_of_vouchers=raw.get("noOfVouchers"),
    )


def _parse_last_voucher(raw: dict) -> VoucherClass | None:
    vobj = raw.get("voucherObj")
    if not vobj:
        return None
    return _parse_voucher(vobj)


def _current_month_totals(vouchers: list[VoucherClass]) -> tuple[float, float]:
    monthly: dict[str, list[float]] = defaultdict(lambda: [0.0, 0.0])
    for v in vouchers:
        dt = v.voucherDate_dt or (parse_wcf_date(v.voucherDate) if v.voucherDate else None)
        if dt and v.consumptionQTY is not None:
            try:
                key = dt.strftime("%Y-%m")
                monthly[key][0] += v.consumptionQTY or 0.0
                monthly[key][1] += v.consumptionPrice or 0.0
            except (TypeError, IndexError):
                pass
    if not monthly:
        return 0.0, 0.0
    latest = sorted(monthly.keys())[-1]
    return monthly[latest][0], monthly[latest][1]


def _current_year_total(vouchers: list[VoucherClass]) -> float:
    year = str(datetime.now().year)
    total = 0.0
    for v in vouchers:
        dt = v.voucherDate_dt or (parse_wcf_date(v.voucherDate) if v.voucherDate else None)
        if dt and str(dt.year) == year and v.consumptionQTY is not None:
            total += v.consumptionQTY
    return total
