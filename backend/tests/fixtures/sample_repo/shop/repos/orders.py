class OrderRepo:
    """In-memory order storage."""

    def __init__(self):
        self._orders = {}

    def get(self, order_id: int):
        return self._orders.get(order_id)

    def cancel(self, order_id: int):
        order = self._orders.pop(order_id, None)
        return {"cancelled": order is not None}


def calculate_discount(total: float, loyalty_years: int) -> float:
    """Loyal customers get 2% per year, capped at 10%."""
    return total * min(0.02 * loyalty_years, 0.10)
