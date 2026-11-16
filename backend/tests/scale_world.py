"""S13 B: a 40-shop pretend world with realistic delays, for measuring and testing monitoring at scale.

Times are SIMULATED seconds, run `SCALE` times faster (SCALE = 0.02: one simulated second takes 20 ms), so a
15-minute round fits in a test. `projected(real)` turns a measured wall time back into simulated seconds.

Per call (simulated): DNS answer 0.1 s, opening the page 0.6 s, reading the certificate 0.3 s, GoDaddy 0.4 s.
Some shops are slow (8 s to open), one hangs (a call that ignores its own timeout: 300 s), one fails (its
padlock is broken, so the https check retries with its real back-off: 2 minutes).
"""

import threading
import time
from collections import deque
from urllib.parse import urlsplit

from tests.conftest import publish, sign_in
from tests.test_m3_launch import approve, meera, plan

SCALE = 0.02
N_SHOPS = 40
HANG, FAIL, SLOW = "shop07", "shop13", {"shop21", "shop22", "shop23"}
COST = {"dns": 0.1, "fetch": 0.6, "cert": 0.3, "godaddy": 0.4, "slow_fetch": 8.0, "hang": 300.0}


def projected(real_seconds: float) -> float:
    return real_seconds / SCALE


def build_shops(client, engine, n: int = N_SHOPS) -> list[dict]:
    sign_in(client, "owner@example.org")  # guest shops aren't watched
    shops = []
    for i in range(n):
        biz = meera(client, subdomain=f"shop{i:02d}")
        p = approve(client, plan(client, biz))
        assert p["status"] == "done", p["steps"]
        publish(engine, biz["id"])
        shops.append(biz)
    return shops


class SlowWorld:
    """Wraps the pretend world's DNS, web, certificate and GoDaddy calls with per-shop delays."""

    def __init__(self, integ, scale: float = SCALE):
        self.integ, self.scale = integ, scale
        self.release = threading.Event()  # set at the end of a test so the hanging call returns
        self.godaddy_calls: deque[float] = deque()
        self.lock = threading.Lock()
        self.busy: dict[str, int] = {}  # host -> calls in progress right now (to see overlap)
        self.max_busy = 0
        http, dns, gd = integ.http, integ.dns, integ.godaddy
        self._fetch, self._cert, self._resolve = http.fetch, http.cert_expires, dns.resolve
        self._records = gd.get_records
        http.fetch, http.cert_expires = self.fetch, self.cert_expires
        dns.resolve = self.resolve  # the pretend resolver has resolve() only; lookup() goes through it
        gd.get_records = self.get_records
        integ.sleep = lambda s: time.sleep(s * scale)
        http.broken_cert.add(f"{FAIL}.localhost")

    def wait(self, simulated: float) -> None:
        time.sleep(simulated * self.scale)

    @staticmethod
    def shop_of(host: str) -> str:
        return (host or "").split(".")[0]

    def _track(self, host: str, fn):
        with self.lock:
            self.busy[host] = self.busy.get(host, 0) + 1
            self.max_busy = max(self.max_busy, sum(self.busy.values()))
        try:
            return fn()
        finally:
            with self.lock:
                self.busy[host] -= 1

    def fetch(self, url: str):
        host = urlsplit(url).hostname or ""
        shop = self.shop_of(host)

        def go():
            if shop == HANG:
                self.release.wait(COST["hang"] * self.scale)
            else:
                self.wait(COST["slow_fetch"] if shop in SLOW else COST["fetch"])
            return self._fetch(url)

        return self._track(host, go)

    def cert_expires(self, host: str):
        self.wait(COST["cert"])
        return self._cert(host)

    def resolve(self, name: str, rtype: str):
        self.wait(COST["dns"])
        return self._resolve(name, rtype)

    def get_records(self, zone: str):
        self.wait(COST["godaddy"])
        got = self._records(zone)  # the client's rate limiter (if any) runs in here
        with self.lock:
            self.godaddy_calls.append(time.monotonic())  # counted when GoDaddy would have answered
        return got

    def most_godaddy_calls_in_a_minute(self) -> int:
        """Most GoDaddy calls in any one SIMULATED minute."""
        window = 60 * self.scale
        times, best, j = list(self.godaddy_calls), 0, 0
        for i, t in enumerate(times):
            while times[j] < t - window:
                j += 1
            best = max(best, i - j + 1)
        return best
