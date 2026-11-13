"""Money as text for sentences: integer cents to "1,234.56" (rule 1: money is integer cents everywhere)."""


def text(cents):
    """Integer cents as a plain amount with thousands separators, e.g. -123456 -> "-1,234.56"."""
    sign = "-" if cents < 0 else ""
    cents = abs(cents)
    return f"{sign}{cents // 100:,}.{cents % 100:02d}"
