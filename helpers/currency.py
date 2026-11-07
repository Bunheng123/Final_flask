from decimal import Decimal, ROUND_HALF_UP

KHR_PER_USD = Decimal('4100')


def _to_decimal(value):
    if value is None:
        return Decimal('0')
    return Decimal(str(value)).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)


def normalize_khr(value):
    if value is None:
        return 0
    return int(Decimal(str(value)).quantize(Decimal('1'), rounding=ROUND_HALF_UP))


def usd_from_khr(khr_value):
    khr_amount = Decimal(str(khr_value or 0))
    usd_amount = (khr_amount / KHR_PER_USD).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
    return usd_amount


def khr_from_usd(usd_value):
    usd_amount = Decimal(str(usd_value or 0))
    khr_amount = (usd_amount * KHR_PER_USD).quantize(Decimal('1'), rounding=ROUND_HALF_UP)
    return int(khr_amount)


def khr_format(khr_value):
    return f"{normalize_khr(khr_value):,.0f} ៛"


def usd_format(khr_value):
    usd_amount = usd_from_khr(khr_value)
    return f"≈ ${usd_amount:,.2f}"
