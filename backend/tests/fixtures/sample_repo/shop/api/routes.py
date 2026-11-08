from fastapi import FastAPI

from shop.services.auth import AuthService
from shop.repos.orders import OrderRepo

app = FastAPI()
auth = AuthService(secret="change-me")
orders = OrderRepo()


@app.post("/login")
def login(username: str, password: str):
    """Exchange credentials for an access token."""
    return {"token": auth.issue_token(username)}


@app.get("/orders/{order_id}")
def get_order(order_id: int):
    return orders.get(order_id)


@app.delete("/orders/{order_id}")
def cancel_order(order_id: int):
    return orders.cancel(order_id)
