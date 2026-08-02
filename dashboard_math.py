"""Pure calculation helpers shared by the browser dashboard and unit tests."""

from __future__ import annotations


def infer_ratio_counts(
    values: dict[str, float], max_total: int = 10_000
) -> dict[str, int]:
    """Recover integer counts from a complete distribution rounded to 2 decimals."""
    items = list(values.items())
    if not items or abs(sum(value for _, value in items) - 100) > 0.2:
        return {}
    for total in range(1, max_total + 1):
        counts = [int(total * percentage / 100 + 0.5) for _, percentage in items]
        if sum(counts) != total:
            continue
        if all(
            round(count / total * 100 + 1e-12, 2) == round(percentage, 2)
            for count, (_, percentage) in zip(counts, items)
        ):
            return {name: count for (name, _), count in zip(items, counts)}
    return {}
