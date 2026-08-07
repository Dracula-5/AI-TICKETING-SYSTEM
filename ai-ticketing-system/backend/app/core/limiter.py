"""
Shared slowapi Limiter instance. Lives in its own module (rather than
app/main.py) so router modules can apply per-route limits — e.g.
@limiter.limit("20/minute") on /auth/login — without a circular import
back to main.py.
"""
from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address, default_limits=["200/minute"])
