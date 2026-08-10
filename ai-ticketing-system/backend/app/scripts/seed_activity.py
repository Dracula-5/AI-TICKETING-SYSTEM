"""
Seeds ~28 additional demo users (customers + ticket providers) with
realistic, backdated activity: tickets running the real category/priority
classifiers through a full status funnel (some open, some bargained and
resolved), plus marketplace negotiations and orders against the existing
6 category vendors and their products.

Usage:
    python -m app.scripts.seed_activity

Idempotent: skips everything if any @shopper-demo.com user already exists.
Not wired into app startup -- manual-only, matching reset_marketplace.py's
precedent, so a routine `uvicorn --reload` can never trigger this.

Not a single atomic transaction: notify() commits internally as it persists
each Notification row, so a run that crashes partway through can't be
cleanly rolled back. If that happens, clean up manually (delete users
matching '%@shopper-demo.com' or '%@provider-demo.com' -- tickets/orders/
negotiations belonging to them become orphaned rows you'd want to remove
too) and rerun. Same robustness level seed_marketplace.py already has.
"""
import asyncio
import random
from datetime import datetime, timedelta

from faker import Faker

from app.ai.priority import predict_priority
from app.core.security import get_password_hash
from app.db.database import SessionLocal
from app.db.models import (
    NegotiationMessage, NegotiationSession, Notification, Order, PriceNegotiation,
    Product, ProviderCategory, Ticket, TicketComment, User, Vendor,
)
from app.routers.ticket import _notify_ticket_providers
from app.services.auto_router import predict_category
from app.services.notification_service import notify
from app.services.seed_users import create_default_tenant

fake = Faker()

CUSTOMER_COUNT = 24
PROVIDER_COUNT = 4
TICKET_COUNT = 50
NEGOTIATION_COUNT = 35
ORDER_COUNT = 45
DAYS_BACK = 30

SLA_HOURS = {"critical": 2, "high": 6, "medium": 12, "low": 24}

# One entry per line hits a specific auto_router.py / priority.py keyword
# rule on purpose, so seeded tickets exercise the real classifiers instead
# of being hand-labeled.
TICKET_BANK = [
    ("WiFi keeps disconnecting in the east wing", "Our office wifi drops every few minutes and it's affecting client calls. Please look into it immediately."),
    ("Server down since this morning", "The main application server has been down since 9am and nobody can access the system. This is an emergency."),
    ("Slow internet connection", "Internet has been really slow the last two days, sometimes it's fine but often unusable."),
    ("New laptop software installation request", "Need the design software installed on my new computer before Monday's presentation."),
    ("Network printer not connecting", "The network printer on the 3rd floor isn't showing up on any computer on the network."),
    ("Power outage in building B", "There's been a power outage in building B since this morning, we need the generator switched on immediately."),
    ("Flickering lights in conference room", "The lights in the main conference room keep flickering, sometimes it goes off completely."),
    ("Broken light fixture in lobby", "The overhead light fixture in the lobby is broken and hanging loose, could be a safety hazard."),
    ("Electric socket not working", "One of the electric sockets near my desk stopped working."),
    ("Generator maintenance request", "The backup generator needs its scheduled maintenance check this week."),
    ("Water leak under the sink", "There's a water leak under the kitchen sink on the 2nd floor, the pipe seems damaged."),
    ("Toilet not flushing properly", "The toilet in the ground floor restroom isn't flushing properly."),
    ("Pipe burst in basement", "A pipe burst in the basement storage area, water everywhere, need urgent help."),
    ("Low water pressure", "Water pressure in the plumbing system has been low all week, sometimes barely a trickle."),
    ("Leaking faucet in restroom", "There's a slow leak from the faucet in the 3rd floor restroom, wasting water."),
    ("ICU oxygen supply concern", "Need urgent verification of the oxygen supply line to the ICU, this is life threatening if not addressed."),
    ("Patient monitor malfunction", "The patient monitor in room 204 is showing erratic readings, the doctor needs it fixed immediately."),
    ("Medical equipment calibration", "The medical equipment in the diagnostics room needs its scheduled calibration."),
    ("Hospital bed repair request", "One of the hospital beds in ward 3 has a broken adjustment mechanism."),
    ("Doctor's office AC not cooling", "The air conditioning in the doctor's office isn't cooling properly, sometimes it works fine."),
    ("Security camera offline in parking lot", "The security camera covering the parking lot has been offline since last night."),
    ("Suspected theft in storage room", "We suspect a theft occurred in the storage room, some equipment is missing. Need this investigated urgently."),
    ("Guard station intercom broken", "The intercom at the main guard station stopped working."),
    ("Access card not working", "My security access card stopped working at the main entrance."),
    ("Camera footage request", "Need to review security camera footage from yesterday evening for an incident report."),
    ("Office chair replacement request", "My office chair is broken and needs replacement, the armrest fell off."),
    ("Meeting room booking conflict", "There's a scheduling conflict for the meeting room booking system."),
    ("Cleaning request for break room", "The break room needs a deep cleaning, it's been neglected for a while."),
    ("Parking spot allocation query", "I have a question about my assigned parking spot allocation."),
    ("General facility feedback", "Just wanted to share some feedback about the facility amenities."),
]

COMMENT_BANK = [
    "Thanks for looking into this, let me know if you need more details.",
    "Any update on this? It's been a couple of days.",
    "This is still happening, please prioritize.",
    "Confirmed the issue is resolved on my end, thank you!",
    "I can be available this afternoon if someone needs to check in person.",
]


def _rand_time_between(start: datetime, end: datetime) -> datetime:
    delta = end - start
    return start + timedelta(seconds=random.uniform(0, max(delta.total_seconds(), 1)))


def _unique_email(db, base: str) -> str:
    email = base
    suffix = 1
    while db.query(User).filter(User.email == email).first():
        suffix += 1
        email = base.replace("@", f"{suffix}@")
    return email


def _create_customers(db, tenant_id: int) -> list[User]:
    customers = []
    for _ in range(CUSTOMER_COUNT):
        name = fake.name()
        email = _unique_email(db, f"{name.lower().replace(' ', '.')}@shopper-demo.com")
        user = User(
            name=name, email=email, hashed_password=get_password_hash("customer123"),
            role="customer", tenant_id=tenant_id,
        )
        db.add(user)
        db.flush()
        customers.append(user)
    return customers


def _create_providers(db, tenant_id: int) -> list[User]:
    providers = []
    for _ in range(PROVIDER_COUNT):
        name = fake.name()
        email = _unique_email(db, f"{name.lower().replace(' ', '.')}@provider-demo.com")
        user = User(
            name=name, email=email, hashed_password=get_password_hash("provider123"),
            role="provider", tenant_id=tenant_id,
        )
        db.add(user)
        db.flush()
        providers.append(user)

    # 3 of 4 get category preferences (exercises real routing in
    # _notify_ticket_providers); the 4th stays a generalist on purpose, to
    # exercise the "nobody has preferences -> everyone hears everything"
    # fallback path too.
    assignments = [
        (providers[0], ["IT Support"]),
        (providers[1], ["Electrical", "Plumbing"]),
        (providers[2], ["Medical"]),
    ]
    for provider, categories in assignments:
        for category in categories:
            db.add(ProviderCategory(user_id=provider.id, category=category))
    db.flush()
    return providers


async def _notify_at(db, when: datetime, *args, **kwargs):
    entry = await notify(db, *args, **kwargs)
    if entry:
        entry.created_at = when
        db.commit()
    return entry


async def _seed_tickets(db, tenant_id: int, customers: list[User], providers: list[User]):
    now = datetime.utcnow()
    all_providers = providers  # the 4 new ones; category-matching handled below
    providers_by_category: dict[str, list[User]] = {}
    for row in db.query(ProviderCategory).filter(ProviderCategory.user_id.in_([p.id for p in providers])).all():
        providers_by_category.setdefault(row.category, []).append(
            next(p for p in providers if p.id == row.user_id)
        )
    generalists = [p for p in providers if p.id not in {u.id for lst in providers_by_category.values() for u in lst}]

    def pick_provider(category: str) -> User:
        candidates = providers_by_category.get(category) or generalists or all_providers
        return random.choice(candidates)

    for _ in range(TICKET_COUNT):
        title, description = random.choice(TICKET_BANK)
        customer = random.choice(customers)
        category = predict_category(title, description)
        priority = predict_priority(description)

        base_time = now - timedelta(days=random.uniform(1, DAYS_BACK))
        sla_due = base_time + timedelta(hours=SLA_HOURS.get(priority, 24))

        ticket = Ticket(
            title=title, description=description, priority=priority, category=category,
            tenant_id=tenant_id, created_by_user_id=customer.id,
            sla_due=sla_due, created_at=base_time, updated_at=base_time,
        )
        db.add(ticket)
        db.flush()

        await _notify_ticket_providers(db, ticket)
        for n in db.query(Notification).filter(Notification.link == f"/ticket/{ticket.id}").all():
            n.created_at = base_time
        db.commit()

        bucket = random.choices(
            ["open", "negotiating", "in-progress", "resolved", "closed"],
            weights=[30, 15, 15, 25, 15],
        )[0]

        if bucket == "open":
            # Leave sla_due in the past for some so the live 30s background
            # thread (app.services.sla_monitor.check_sla) escalates them for
            # free -- no need to hand-simulate escalation here.
            continue

        provider = pick_provider(category)
        ticket.assigned_to_user_id = provider.id
        offer_time = base_time + timedelta(hours=random.uniform(1, 6))
        offer_amount = round(random.uniform(500, 15000), 2)

        offer = PriceNegotiation(
            ticket_id=ticket.id, sender_user_id=customer.id, sender_role="customer",
            action="offer", amount=offer_amount, message="What would this cost to fix?",
            created_at=offer_time,
        )
        db.add(offer)
        ticket.pricing_status = "negotiating"
        ticket.status = "negotiating"
        db.commit()
        await _notify_at(db, offer_time, tenant_id, provider.id, type_="ticket_offer",
                          title=f"New offer on '{ticket.title}'", message=f"Customer offered Rs {offer_amount}",
                          link=f"/ticket/{ticket.id}")

        if bucket == "negotiating":
            continue

        # in-progress / resolved / closed all require a finalized price.
        final_time = offer_time + timedelta(hours=random.uniform(1, 12))
        accept = PriceNegotiation(
            ticket_id=ticket.id, sender_user_id=provider.id, sender_role="provider",
            action="accept", amount=offer_amount, message="Sounds good, I can do it for that.",
            is_final=True, created_at=final_time,
        )
        db.add(accept)
        ticket.final_price = offer_amount
        ticket.pricing_status = "finalized"
        ticket.price_finalized_at = final_time
        ticket.status = bucket
        ticket.updated_at = final_time
        db.commit()
        await _notify_at(db, final_time, tenant_id, customer.id, type_="ticket_accepted",
                          title=f"Deal finalized on '{ticket.title}'", message=f"Accepted at Rs {offer_amount}",
                          link=f"/ticket/{ticket.id}")

        if random.random() < 0.4:
            for _ in range(random.randint(1, 2)):
                comment_time = _rand_time_between(offer_time, final_time)
                db.add(TicketComment(
                    ticket_id=ticket.id, content=random.choice(COMMENT_BANK), created_at=comment_time,
                ))
            db.commit()


async def _seed_marketplace_activity(db, tenant_id: int, customers: list[User]):
    now = datetime.utcnow()
    products = db.query(Product).all()
    if not products:
        return

    accepted_sessions: list[NegotiationSession] = []

    for _ in range(NEGOTIATION_COUNT):
        product = random.choice(products)
        vendor = db.query(Vendor).filter(Vendor.id == product.vendor_id).first()
        customer = random.choice(customers)
        base_time = now - timedelta(days=random.uniform(1, DAYS_BACK))
        opening_amount = round(product.price * random.uniform(0.5, 0.85), 2)

        session = NegotiationSession(
            tenant_id=tenant_id, product_id=product.id, customer_id=customer.id,
            vendor_id=vendor.id, status="open", current_offer_price=opening_amount,
            created_at=base_time,
        )
        db.add(session)
        db.flush()

        opening = NegotiationMessage(
            session_id=session.id, sender_role="customer", sender_user_id=customer.id,
            message_type="offer", amount=opening_amount, text_content="Would you take this?",
            created_at=base_time,
        )
        db.add(opening)
        db.commit()
        await _notify_at(db, base_time, tenant_id, vendor.user_id, type_="negotiation_started",
                          title="New price negotiation",
                          message=f"{customer.name} offered {product.currency} {opening_amount:.2f} for '{product.title}'",
                          link=f"/negotiation/{session.id}")

        # No auto-negotiate engine anymore -- simulate a real vendor either
        # accepting outright, countering with their own number, or not
        # having replied yet (all three are realistic demo states).
        reply_time = base_time + timedelta(minutes=random.uniform(5, 90))
        reply_roll = random.random()
        if reply_roll < 0.4:
            accept_entry = NegotiationMessage(
                session_id=session.id, sender_role="vendor", sender_user_id=vendor.user_id,
                message_type="accept", amount=opening_amount, created_at=reply_time,
            )
            db.add(accept_entry)
            session.status = "accepted"
            session.current_offer_price = opening_amount
            session.closed_at = reply_time
            db.commit()
            await _notify_at(db, reply_time, tenant_id, customer.id, type_="negotiation_accepted",
                              title="Deal accepted",
                              message=f"Negotiation accepted at {product.currency} {opening_amount:.2f}",
                              link=f"/negotiation/{session.id}")
        elif reply_roll < 0.75:
            counter_amount = round(random.uniform(opening_amount, product.price), 2)
            counter_entry = NegotiationMessage(
                session_id=session.id, sender_role="vendor", sender_user_id=vendor.user_id,
                message_type="counter_offer", amount=counter_amount, created_at=reply_time,
            )
            db.add(counter_entry)
            session.current_offer_price = counter_amount
            db.commit()
            await _notify_at(db, reply_time, tenant_id, customer.id, type_="negotiation_message",
                              title=f"Vendor responded on '{product.title}'",
                              message=f"Offer: {product.currency} {counter_amount:.2f}",
                              link=f"/negotiation/{session.id}")
        # else: leave the session open with just the customer's opening offer

        if session.status == "accepted":
            accepted_sessions.append(session)

    order_count = 0
    for session in accepted_sessions:
        if order_count >= ORDER_COUNT:
            break
        product = db.query(Product).filter(Product.id == session.product_id).first()
        if not product or product.stock_quantity < 1:
            continue
        order_time = session.closed_at + timedelta(hours=random.uniform(0.5, 8)) if session.closed_at else now
        await _place_order(db, tenant_id, session.customer_id, product, session.current_offer_price, session.id, order_time)
        order_count += 1

    while order_count < ORDER_COUNT:
        product = random.choice(products)
        if product.stock_quantity < 1:
            continue
        customer = random.choice(customers)
        order_time = now - timedelta(days=random.uniform(1, DAYS_BACK))
        await _place_order(db, tenant_id, customer.id, product, product.price, None, order_time)
        order_count += 1


async def _place_order(db, tenant_id, customer_id, product, unit_price, negotiation_session_id, order_time):
    quantity = random.randint(1, 3)
    quantity = min(quantity, product.stock_quantity)
    if quantity < 1:
        return
    product.stock_quantity -= quantity

    status = random.choices(
        ["pending", "confirmed", "shipped", "completed", "cancelled"],
        weights=[15, 20, 20, 38, 7],
    )[0]

    order = Order(
        tenant_id=tenant_id, product_id=product.id, customer_id=customer_id,
        vendor_id=product.vendor_id, negotiation_session_id=negotiation_session_id,
        quantity=quantity, unit_price=unit_price, total_price=round(unit_price * quantity, 2),
        status=status, delivery_address=fake.address().replace("\n", ", "),
        created_at=order_time, updated_at=order_time,
    )
    db.add(order)
    db.commit()

    vendor = db.query(Vendor).filter(Vendor.id == product.vendor_id).first()
    customer = db.query(User).filter(User.id == customer_id).first()
    await _notify_at(
        db, order_time, tenant_id, vendor.user_id, type_="order_placed",
        title="New order received",
        message=f"{customer.name} ordered {quantity} x '{product.title}' ({product.currency} {order.total_price:.2f})",
        link="/vendor/dashboard",
    )
    if status != "pending":
        status_time = order_time + timedelta(hours=random.uniform(1, 48))
        await _notify_at(
            db, status_time, tenant_id, customer_id, type_="order_status_changed",
            title="Order update", message=f"Your order for '{product.title}' is now {status}",
            link="/orders",
        )


async def seed_activity() -> dict:
    db = SessionLocal()
    try:
        already_seeded = db.query(User).filter(User.email.like("%@shopper-demo.com")).first() is not None
        if already_seeded:
            print("Activity already seeded - skipping (delete %@shopper-demo.com / %@provider-demo.com users to reset).")
            return {"customers": 0, "providers": 0, "tickets": 0, "negotiations": 0, "orders": 0}

        tenant_id = create_default_tenant(db)

        customers = _create_customers(db, tenant_id)
        providers = _create_providers(db, tenant_id)
        db.commit()
        print(f"Created {len(customers)} customers, {len(providers)} providers")

        await _seed_tickets(db, tenant_id, customers, providers)
        print("Seeded tickets")

        await _seed_marketplace_activity(db, tenant_id, customers)
        print("Seeded marketplace activity")

        summary = {
            "customers": len(customers),
            "providers": len(providers),
            "tickets": TICKET_COUNT,
            "negotiations": NEGOTIATION_COUNT,
            "orders": ORDER_COUNT,
        }
        print(f"Done: {summary}")
        return summary
    finally:
        db.close()


if __name__ == "__main__":
    asyncio.run(seed_activity())
