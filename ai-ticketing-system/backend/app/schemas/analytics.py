from pydantic import BaseModel


class TopProductOut(BaseModel):
    id: int
    title: str
    views_count: int


class TopVendorOut(BaseModel):
    id: int
    shop_name: str
    revenue: float


class VendorAnalyticsOut(BaseModel):
    total_products: int
    total_views: int
    total_orders: int
    total_revenue: float
    total_negotiations: int
    accepted_negotiations: int
    negotiation_success_rate_pct: float
    top_products: list[TopProductOut]


class AdminAnalyticsOut(BaseModel):
    total_vendors: int
    total_products: int
    total_views: int
    total_orders: int
    total_revenue: float
    total_negotiations: int
    accepted_negotiations: int
    negotiation_success_rate_pct: float
    top_vendors: list[TopVendorOut]
