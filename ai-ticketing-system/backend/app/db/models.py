from sqlalchemy import Column, Integer, String, ForeignKey, DateTime, Text, Boolean, Float
from sqlalchemy.orm import relationship
from datetime import datetime
from app.db.database import Base


class Tenant(Base):
    __tablename__ = "tenants"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, index=True)
    domain = Column(String, unique=True, index=True)

    users = relationship("User", back_populates="tenant")
    tickets = relationship("Ticket", back_populates="tenant")
    providers = relationship("Provider", back_populates="tenant")
    vendors = relationship("Vendor", back_populates="tenant")


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    email = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    role = Column(String)      # admin / provider / customer / service_provider / vendor
    tenant_id = Column(Integer, ForeignKey("tenants.id"))

    tenant = relationship("Tenant", back_populates="users")

    tickets = relationship(
        "Ticket",
        back_populates="created_by_user",
        foreign_keys="Ticket.created_by_user_id"
    )
    price_negotiations = relationship(
        "PriceNegotiation",
        back_populates="sender_user",
        cascade="all, delete"
    )
    vendor_profile = relationship(
        "Vendor",
        back_populates="user",
        uselist=False,
        cascade="all, delete"
    )


class Ticket(Base):
    __tablename__ = "tickets"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String, nullable=False)
    description = Column(Text, nullable=False)
    priority = Column(String, nullable=False)

    category = Column(String, nullable=True)

    status = Column(String, default="open")
    pricing_status = Column(String, default="pending")
    final_price = Column(Float, nullable=True)
    price_finalized_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    tenant_id = Column(Integer, ForeignKey("tenants.id"))
    created_by_user_id = Column(Integer, ForeignKey("users.id"))
    assigned_to_user_id = Column(Integer, ForeignKey("users.id"), nullable=True)

    sla_due = Column(DateTime, nullable=True)
    is_escalated = Column(Boolean, default=False)

    tenant = relationship("Tenant", back_populates="tickets")

    created_by_user = relationship(
        "User",
        foreign_keys=[created_by_user_id]
    )

    assigned_user = relationship(
        "User",
        foreign_keys=[assigned_to_user_id]
    )

    comments = relationship(
        "TicketComment",
        back_populates="ticket",
        cascade="all, delete"
    )
    price_negotiations = relationship(
        "PriceNegotiation",
        back_populates="ticket",
        cascade="all, delete",
        order_by="PriceNegotiation.created_at"
    )


class TicketComment(Base):
    __tablename__ = "ticket_comments"

    id = Column(Integer, primary_key=True)
    content = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)
    ticket_id = Column(Integer, ForeignKey("tickets.id"))

    ticket = relationship("Ticket", back_populates="comments")


class Provider(Base):
    __tablename__ = "providers"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    department = Column(String, nullable=True)
    contact = Column(String, nullable=True)

    tenant_id = Column(Integer, ForeignKey("tenants.id"))

    tenant = relationship("Tenant", back_populates="providers")


class PriceNegotiation(Base):
    __tablename__ = "price_negotiations"

    id = Column(Integer, primary_key=True, index=True)
    ticket_id = Column(Integer, ForeignKey("tickets.id"), nullable=False, index=True)
    sender_user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    sender_role = Column(String, nullable=False)
    action = Column(String, nullable=False)  # offer | counter | accept | reject
    amount = Column(Float, nullable=False)
    message = Column(Text, nullable=True)
    is_final = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    ticket = relationship("Ticket", back_populates="price_negotiations")
    sender_user = relationship("User", back_populates="price_negotiations")


class Vendor(Base):
    __tablename__ = "vendors"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), unique=True, nullable=False, index=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id"), nullable=False, index=True)

    shop_name = Column(String, nullable=False)
    phone_number = Column(String, nullable=False)
    shop_address = Column(String, nullable=False)
    description = Column(Text, nullable=True)
    # One of MARKETPLACE_CATEGORIES (app/core/constants.py); nullable at the DB
    # level for legacy/ad-hoc rows, required by VendorRegister for every new
    # self-registration. Any number of vendors may share a category -- an
    # earlier iteration hard-capped this to one vendor per category, but a
    # real marketplace has many sellers per category, so that constraint was
    # removed (see migration 0007).
    category = Column(String, nullable=True, index=True)

    is_verified = Column(Boolean, default=False)
    rating_avg = Column(Float, default=0.0)
    created_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", back_populates="vendor_profile")
    tenant = relationship("Tenant", back_populates="vendors")
    products = relationship("Product", back_populates="vendor", cascade="all, delete")


class Product(Base):
    __tablename__ = "products"

    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id"), nullable=False, index=True)
    vendor_id = Column(Integer, ForeignKey("vendors.id"), nullable=False, index=True)

    title = Column(String, nullable=False, index=True)
    description = Column(Text, nullable=False)
    category = Column(String, nullable=True, index=True)

    price = Column(Float, nullable=False)
    currency = Column(String, default="INR")
    stock_quantity = Column(Integer, default=0)

    status = Column(String, default="active")  # active / inactive / out_of_stock
    views_count = Column(Integer, default=0)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    tenant = relationship("Tenant")
    vendor = relationship("Vendor", back_populates="products")
    images = relationship(
        "ProductImage",
        back_populates="product",
        cascade="all, delete",
        order_by="ProductImage.sort_order"
    )


class ProductImage(Base):
    __tablename__ = "product_images"

    id = Column(Integer, primary_key=True, index=True)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=False, index=True)
    url = Column(String, nullable=False)
    sort_order = Column(Integer, default=0)

    product = relationship("Product", back_populates="images")


class NegotiationSession(Base):
    __tablename__ = "negotiation_sessions"

    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id"), nullable=False, index=True)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=False, index=True)
    customer_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    vendor_id = Column(Integer, ForeignKey("vendors.id"), nullable=False, index=True)

    status = Column(String, default="open")  # open / accepted / rejected
    current_offer_price = Column(Float, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)
    closed_at = Column(DateTime, nullable=True)

    product = relationship("Product")
    customer = relationship("User", foreign_keys=[customer_id])
    vendor = relationship("Vendor")
    messages = relationship(
        "NegotiationMessage",
        back_populates="session",
        cascade="all, delete",
        order_by="NegotiationMessage.created_at"
    )


class NegotiationMessage(Base):
    __tablename__ = "negotiation_messages"

    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(Integer, ForeignKey("negotiation_sessions.id"), nullable=False, index=True)
    sender_role = Column(String, nullable=False)  # customer / vendor
    sender_user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    message_type = Column(String, nullable=False)  # text / offer / counter_offer / accept / reject
    amount = Column(Float, nullable=True)
    text_content = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    session = relationship("NegotiationSession", back_populates="messages")


class Order(Base):
    __tablename__ = "orders"

    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id"), nullable=False, index=True)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=False, index=True)
    customer_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    vendor_id = Column(Integer, ForeignKey("vendors.id"), nullable=False, index=True)
    negotiation_session_id = Column(Integer, ForeignKey("negotiation_sessions.id"), nullable=True)

    quantity = Column(Integer, default=1)
    unit_price = Column(Float, nullable=False)
    total_price = Column(Float, nullable=False)
    status = Column(String, default="pending")  # pending / confirmed / shipped / completed / cancelled
    delivery_address = Column(String, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    product = relationship("Product")
    customer = relationship("User", foreign_keys=[customer_id])
    vendor = relationship("Vendor")
    negotiation_session = relationship("NegotiationSession")


class Notification(Base):
    __tablename__ = "notifications"

    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)

    type = Column(String, nullable=False)
    title = Column(String, nullable=False)
    message = Column(Text, nullable=True)
    link = Column(String, nullable=True)
    is_read = Column(Boolean, default=False)

    created_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User")


class ProviderCategory(Base):
    __tablename__ = "provider_categories"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    category = Column(String, nullable=False)

    user = relationship("User")
