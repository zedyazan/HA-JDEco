"""Response dataclasses mirroring confirmed JDECo WCFClasses."""

from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
import re
from typing import Optional


def parse_wcf_date(d_str: str | None) -> datetime | None:
    """Parse Microsoft WCF /Date(ms[+tz])/ into timezone-aware datetime."""
    if not d_str or not isinstance(d_str, str):
        return None
    m = re.search(r"/Date\((\d+)([+-]\d{4})?\)/", d_str)
    if m:
        ms = int(m.group(1))
        tz_offset = m.group(2)
        if tz_offset:
            sign = 1 if tz_offset[0] == "+" else -1
            hrs = int(tz_offset[1:3])
            mins = int(tz_offset[3:5])
            tz = timezone(sign * timedelta(hours=hrs, minutes=mins))
            return datetime.fromtimestamp(ms / 1000.0, tz=tz)
        return datetime.fromtimestamp(ms / 1000.0, tz=timezone.utc)
    try:
        return datetime.fromisoformat(d_str)
    except Exception:
        return None


@dataclass
class MeterReading:
    currentReadingKW: Optional[float] = None
    prepaymentBalance: Optional[float] = None
    readingDateTime: Optional[str] = None
    readingDateTime_dt: Optional[datetime] = None
    readingType: Optional[str] = None


@dataclass
class BillFinancialParams:
    paymentAMT: Optional[float] = None
    consQTY: Optional[float] = None


@dataclass
class ChargeDetails:
    paymentAMT: Optional[float] = None
    consQTY: Optional[float] = None
    paymentDate: Optional[str] = None
    paymentDate_dt: Optional[datetime] = None
    receiptNo: Optional[str] = None
    STSToken: Optional[str] = None
    debtAMT: Optional[float] = None
    fixedAMT: Optional[float] = None
    VAT: Optional[float] = None
    consCost: Optional[float] = None
    miscAMT: Optional[float] = None
    deductionAMT: Optional[float] = None
    interestAMT: Optional[float] = None


@dataclass
class TariffClass:
    tarrifNo: Optional[str] = None
    tarrifNameE: Optional[str] = None
    cost: Optional[float] = None


@dataclass
class VoucherClass:
    voucherNo: Optional[str] = None
    voucherDate: Optional[str] = None
    voucherDate_dt: Optional[datetime] = None
    voucherAMT: Optional[float] = None
    paidAMT: Optional[float] = None
    remainAMT: Optional[float] = None
    netAMT: Optional[float] = None
    consumptionQTY: Optional[float] = None
    consumptionPrice: Optional[float] = None
    currentReadingKW: Optional[float] = None
    previousReading: Optional[float] = None
    readingDate: Optional[str] = None
    readingDate_dt: Optional[datetime] = None
    lastDueDate: Optional[str] = None
    lastDueDate_dt: Optional[datetime] = None
    fixedAMT: Optional[float] = None
    VAT: Optional[float] = None
    INTAMT: Optional[float] = None
    totalMISC: Optional[float] = None
    readingType: Optional[str] = None
    STSToken: Optional[str] = None


@dataclass
class AgreementDetails:
    agreeNo: Optional[str] = None
    meterNo: Optional[str] = None
    agreementNick: Optional[str] = None
    usageType: Optional[str] = None
    addressEng: Optional[str] = None
    FName: Optional[str] = None
    LName: Optional[str] = None
    isPrepaidMeter: Optional[bool] = None
    isSmartMeter: Optional[bool] = None
    canChargeRemotely: Optional[bool] = None
    lastMeterReading: Optional[float] = None
    lastMeterReadingDate: Optional[str] = None
    lastMeterReadingDate_dt: Optional[datetime] = None
    totalBalance: Optional[str] = None
    categoryDescA: Optional[str] = None
    categoryDescE: Optional[str] = None
    meterTypeA: Optional[str] = None
    meterTypeE: Optional[str] = None
    meterGeneralAVG: Optional[float] = None
    meterSummerAVG: Optional[float] = None
    meterWinterAVG: Optional[float] = None
    estimatedDaysForNextVoucher: Optional[int] = None
    estimatedNextVoucherAMT: Optional[float] = None
    nextEstimatedChargeDate: Optional[str] = None
    nextExpectedVoucherDate: Optional[str] = None
    smartMeterReading: Optional[MeterReading] = None
    lastPCChargeDetails: Optional[ChargeDetails] = None
    tarrif: Optional[TariffClass] = None
    paidVouchers: list[VoucherClass] = field(default_factory=list)


@dataclass
class KWQtyData:
    result_code: int = -1
    payment_amt: Optional[float] = None
    cons_qty: Optional[float] = None


@dataclass
class DebtData:
    result_code: int = -1
    debt_value: Optional[float] = None
    no_of_vouchers: Optional[int] = None


@dataclass
class CoordinatorData:
    agreement: Optional[AgreementDetails] = None
    kwqty: Optional[KWQtyData] = None
    debt: Optional[DebtData] = None
    last_voucher: Optional[VoucherClass] = None
    monthly_kwh: Optional[float] = None
    monthly_cost: Optional[float] = None
    yearly_kwh: Optional[float] = None
    last_update: Optional[datetime] = None
    error: Optional[str] = None
