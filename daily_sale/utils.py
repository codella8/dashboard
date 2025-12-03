from decimal import Decimal
from django.db.models import Sum, Count, F, Q, Max

def format_decimal_or_blank(v):
    try:
        if v is None:
            return ''
        v = Decimal(v)
        if v == 0:
            return ''
        s = format(v, 'f')
        if '.' in s:
            s = s.rstrip('0').rstrip('.')
        return s
    except Exception:
        return str(v)
