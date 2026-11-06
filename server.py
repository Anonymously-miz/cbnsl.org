#!/usr/bin/env python3
"""
CBN Sierra Leone — LITE website server
======================================
One file. No database. No admin panel. Standard library only.

It does exactly two things:
  1. Serves the static pages in this folder (index.html, donate.html, …).
  2. Powers the donations page:
        POST /api/donate            → creates a Monime checkout session, returns its URL
        GET  /donate/return         → donor comes back from Monime; we ask Monime if it was paid
        GET  /api/donate/status     → donate.html polls this while a payment is pending
        POST /api/monime/webhook    → optional instant notification from Monime
     When Monime confirms a payment, a receipt is emailed to the donor and an
     alert to cbnetwork.sierraleone@gmail.com (Gmail SMTP).

Why is there a server at all?  Monime's API needs the secret access token on
every call. If that token were in the browser, anyone could copy it and take
payments on your account. Keeping it here is the only safe option.

Run:   python3 server.py          then open  http://127.0.0.1:8000/
"""

import hashlib
import hmac
import json
import mimetypes
import os
import posixpath
import re
import secrets
import smtplib
import ssl
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import defaultdict, deque
from datetime import datetime
from email.message import EmailMessage
from email.utils import formataddr, formatdate, make_msgid
from http.server import HTTPServer, BaseHTTPRequestHandler, ThreadingHTTPServer
from dotenv import load_dotenv

ROOT = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(ROOT, "cbn.env"))


# =====================================================================
#  CONFIGURATION  — everything is hard-coded here, as requested.
#  ⚠  This file contains secrets. Keep the static-site folder private
#     (never upload server.py to a public GitHub repo).
# =====================================================================
# Render provides a dynamic PORT and expects the app to bind to all interfaces.
HOST = os.environ.get("HOST") or os.environ.get("CBN_HOST") or "0.0.0.0"
PORT = int(os.environ.get("PORT") or os.environ.get("CBN_PORT") or "8000")


# Monime / email settings live in the env file and are exposed here as Python
# names for the rest of the app.
MONIME_SPACE_ID       = os.environ.get("MONIME_SPACE_ID", "")
MONIME_ACCESS_TOKEN   = os.environ.get("MONIME_ACCESS_TOKEN", "")
MONIME_WEBHOOK_SECRET = os.environ.get("MONIME_WEBHOOK_SECRET", "")
MONIME_MODE           = os.environ.get("MONIME_MODE", "test")
MONIME_API            = os.environ.get("MONIME_API", "https://api.monime.io")
MONIME_VERSION        = os.environ.get("MONIME_VERSION", "caph.2025-08-23")
SMTP_HOST             = os.environ.get("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT             = int(os.environ.get("SMTP_PORT", "587"))
SMTP_USER             = os.environ.get("SMTP_USER", "")
SMTP_PASS             = os.environ.get("SMTP_PASS", "")
FROM_NAME             = os.environ.get("FROM_NAME", "CBN Sierra Leone")
OFFICE_EMAIL          = os.environ.get("OFFICE_EMAIL", SMTP_USER)
PUBLIC_BASE_URL       = os.environ.get("PUBLIC_BASE_URL", "")
ALLOWED_ORIGINS = tuple(
    origin.strip()
    for origin in os.environ.get(
        "ALLOWED_ORIGINS",
        "http://localhost:3000,http://127.0.0.1:3000,https://localhost:3000,"
        "https://cbnslorg.vercel.app,https://cbnsl.org,https://www.cbnsl.org",
    ).split(",")
    if origin.strip()
)

# Public https:// address of the site once deployed (used for Monime's return
# links and the webhook). Leave "" while testing locally — the address in the
# browser bar is used instead.


ORG_NAME       = "Community Builders Network - Sierra Leone"
OFFICE_ADDRESS = "112 Bai Bureh Road, Grassfield, Freetown, Sierra Leone"
OFFICE_PHONE   = "+232 78 940 635"

# --- Donation rules ------------------------------------------------------
MIN_AMOUNT_SLL = 5_000          # amounts on the site are shown in old Leones (Le)
MAX_AMOUNT_SLL = 100_000_000
PROJECTS = {                    # value sent by donate.html  →  label shown on receipts
    "safe-water-kono-district":          "Safe Water for Kono District",
    "girls-education-initiative":        "Girls' Education Initiative",
    "womens-farming-cooperatives":       "Women's Farming Cooperatives",
    "rebuilding-rural-primary-schools":  "Rebuilding Rural Primary Schools",
    "maternal-child-health-outreach":    "Maternal & Child Health Outreach",
    "youth-vocational-skills-programme": "Youth Vocational Skills Programme",
}

# Sierra Leone mobile-money prefixes (first two digits after +232)
ORANGE_PREFIXES   = ("72", "73", "74", "75", "76", "77", "78", "79")
AFRICELL_PREFIXES = ("30", "31", "32", "33", "34", "77", "88", "99")
# =====================================================================

RECEIPT_LOG = os.path.join(ROOT, "receipts-sent.txt")   # one reference per line — stops duplicate receipts
ALLOWED_EXT = {".html", ".css", ".js", ".png", ".jpg", ".jpeg", ".gif", ".svg", ".ico", ".webp", ".woff", ".woff2"}
SECURITY_HEADERS = [
    ("X-Content-Type-Options", "nosniff"),
    ("X-Frame-Options", "DENY"),
    ("Referrer-Policy", "strict-origin-when-cross-origin"),
    ("Content-Security-Policy",
     "default-src 'self'; img-src 'self' https://images.pexels.com data:; "
     "style-src 'self' 'unsafe-inline'; script-src 'self' 'unsafe-inline'; "
     "connect-src 'self'; frame-ancestors 'none'; base-uri 'self'"),
]
REF_RE = re.compile(r"^CBN-[A-Z0-9]{6,10}$")
EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")

# In-memory state (the only "storage" this server has)
_LOCK = threading.Lock()
SESSIONS = {}        # ref → donation dict (donor details + Monime session id)
COMPLETED = set()    # refs that already received a receipt (also persisted in receipts-sent.txt)


# ---------------------------------------------------------------------
# small helpers
# ---------------------------------------------------------------------
def clean(v, n=200):
    return str(v if v is not None else "").strip()[:n]


def valid_email(e):
    return bool(e) and bool(EMAIL_RE.match(e)) and len(e) <= 254


def sll_to_minor(sll):
    """Old Leones shown on the site → Monime minor units of the new Leone.
    Le 250,000 (SLL) = SLE 250.00 = 25000 minor units."""
    return int(round(int(sll) / 1000 * 100))


def fmt_sle(minor):
    return f"SLE {int(minor) / 100:,.2f}"


def normalise_sl(raw):
    d = re.sub(r"\D", "", raw or "")
    if d.startswith("232"):
        d = d[3:]
    if len(d) == 9 and d.startswith("0"):
        d = d[1:]
    return d if len(d) == 8 else ""


def validate_momo(raw, operator):
    local = normalise_sl(raw)
    if not local:
        return None, "Please enter a valid Sierra Leone mobile number (8 digits after +232)."
    p = local[:2]
    is_or, is_af = p in ORANGE_PREFIXES, p in AFRICELL_PREFIXES
    if operator == "orange" and not is_or:
        return None, ("That is an Africell number — choose Africell Money, or enter an Orange number (072–079)."
                      if is_af else "That is not an Orange Sierra Leone number (Orange numbers start with 072–079).")
    if operator == "africell" and not is_af:
        return None, ("That is an Orange number — choose Orange Money, or enter an Africell number (030–034, 077, 088, 099)."
                      if is_or else "That is not an Africell Sierra Leone number (030–034, 077, 088 or 099).")
    return "+232" + local, "ok"


def ssl_ctx():
    cafile = None
    try:
        import certifi
        cafile = certifi.where()
    except Exception:
        cafile = os.environ.get("SSL_CERT_FILE") or None
    ctx = ssl.create_default_context(cafile=cafile)
    ctx.minimum_version = ssl.TLSVersion.TLSv1_2
    return ctx


def load_completed():
    try:
        with open(RECEIPT_LOG, encoding="utf-8") as f:
            for line in f:
                ref = line.strip().split()[0] if line.strip() else ""
                if ref:
                    COMPLETED.add(ref)
    except FileNotFoundError:
        pass


def mark_completed(ref):
    """True the FIRST time a reference is completed (so receipts go out once)."""
    with _LOCK:
        if ref in COMPLETED:
            return False
        COMPLETED.add(ref)
        try:
            with open(RECEIPT_LOG, "a", encoding="utf-8") as f:
                f.write(f"{ref} {datetime.now():%Y-%m-%d %H:%M:%S}\n")
        except OSError as e:
            print(f"[lite] could not write {RECEIPT_LOG}: {e}")
        return True


# ---------------------------------------------------------------------
# per-IP rate limiting
# ---------------------------------------------------------------------
_RL = defaultdict(deque)
_RL_LOCK = threading.Lock()
LIMITS = {"donate": (6, 600), "status": (120, 600), "webhook": (60, 60)}


def rate_ok(bucket, ip):
    limit, window = LIMITS[bucket]
    now = time.monotonic()
    with _RL_LOCK:
        dq = _RL[f"{bucket}:{ip}"]
        while dq and now - dq[0] > window:
            dq.popleft()
        if len(dq) >= limit:
            return False
        dq.append(now)
        return True


# ---------------------------------------------------------------------
# Monime API
# cspell:ignore monime Monime
# ---------------------------------------------------------------------
def monime(method, path, body=None, idem=None):
    """→ (ok, http_status, payload). Never raises."""
    headers = {
        "Authorization": f"Bearer {MONIME_ACCESS_TOKEN}",
        "Monime-Space-Id": MONIME_SPACE_ID,
        "Monime-Version": MONIME_VERSION,
        "Accept": "application/json",
        "User-Agent": "CBN-SierraLeone-Lite/1.0",
    }
    data = None
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"
    if idem:
        headers["Idempotency-Key"] = idem[:64]
    req = urllib.request.Request(MONIME_API + path, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=25, context=ssl_ctx()) as r:
            raw = r.read().decode("utf-8", "replace")
            return True, r.status, (json.loads(raw) if raw else {})
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", "replace") if e.fp else ""
        try:
            return False, e.code, json.loads(raw) if raw else {}
        except json.JSONDecodeError:
            return False, e.code, raw
    except Exception as e:
        return False, 0, f"NETWORK: {type(e).__name__}: {e}"


def monime_error(payload, code):
    if isinstance(payload, dict):
        msgs = payload.get("messages")
        if isinstance(msgs, list) and msgs:
            m = msgs[0]
            return (m.get("message") or m.get("detail") or json.dumps(m)) if isinstance(m, dict) else str(m)
        return payload.get("message") or payload.get("error") or json.dumps(payload)[:200]
    if isinstance(payload, str) and payload.startswith("NETWORK:"):
        return payload
    return {401: "Monime rejected the access token (401) — check MONIME_ACCESS_TOKEN / MONIME_SPACE_ID.",
            403: "Monime refused the request (403).", 404: "Not found at Monime (404)."}.get(code, f"Monime error HTTP {code}")


def create_checkout(d, base):
    ref, minor = d["ref"], sll_to_minor(d["amount"])
    title = PROJECTS.get(d.get("project") or "", "")
    name = ("Donation — " + title) if title else "Donation to Community Builders Network"
    body = {
        "name": name[:150],
        "description": (f"Thank you {d['first']} {d['last']}! Reference {ref}. "
                        f"100% of your gift reaches communities in Sierra Leone.")[:1000],
        "reference": ref,
        "callbackState": ref,
        "successUrl": f"{base}/donate/return?ref={ref}&outcome=success",
        "cancelUrl":  f"{base}/donate/return?ref={ref}&outcome=cancel",
        "lineItems": [{
            "type": "custom", "name": name[:100],
            "price": {"currency": "SLE", "value": minor}, "quantity": 1,
            "reference": ref, "description": (title or "General fund")[:100],
        }],
        "brandingOptions": {"primaryColor": "#f36f21"},
        # Metadata travels with the session, so even after a server restart we can
        # rebuild the receipt from what Monime returns.
        "metadata": {
            "donation_reference": ref,
            "donor_name":  f"{d['first']} {d['last']}"[:100],
            "donor_email": d["email"][:100],
            "amount_sll":  str(d["amount"]),
            "method":      d["method"],
            "project":     (d.get("project") or "general")[:100],
            "source":      "cbn-website-lite",
        },
    }
    po = {
        "orange_money":   {"momo": {"enabledProviders": ["m17"]}},
        "africell_money": {"momo": {"enabledProviders": ["m18"]}},
        "card":           {"momo": {"disable": True}, "bank": {"disable": True}},
    }.get(d["method"])
    if po:
        body["paymentOptions"] = po
    ok, code, payload = monime("POST", "/v1/checkout-sessions", body, idem=f"cbn-lite-{ref}")
    if not ok:
        return False, monime_error(payload, code)
    result = payload.get("result") if isinstance(payload, dict) else None
    if not result or not result.get("redirectUrl"):
        return False, f"Monime returned no checkout URL: {json.dumps(payload)[:200]}"
    return True, result


def find_session(ref):
    """Session id for a reference — from memory, or by asking Monime (survives restarts)."""
    rec = SESSIONS.get(ref)
    if rec and rec.get("session_id"):
        return rec["session_id"], rec
    after = None
    for _ in range(6):                                   # scan up to 300 recent sessions
        q = "/v1/checkout-sessions?limit=50" + (f"&after={urllib.parse.quote(after)}" if after else "")
        ok, code, payload = monime("GET", q)
        if not ok:
            break
        for s in (payload.get("result") or []):
            if s.get("reference") == ref:
                return s["id"], {"session_id": s["id"], "from_monime": True}
        after = (payload.get("pagination") or {}).get("next")
        if not after:
            break
    return None, None


def donation_info(ref, session, rec):
    md = session.get("metadata") or {}
    rec = rec or {}
    try:
        amount = int(rec.get("amount") or md.get("amount_sll") or 0)
    except (TypeError, ValueError):
        amount = 0
    name = (f"{rec.get('first','')} {rec.get('last','')}".strip()) or md.get("donor_name") or "Donor"
    return {
        "ref": ref, "name": name, "first": (rec.get("first") or name.split(" ")[0]),
        "email": rec.get("email") or md.get("donor_email") or "",
        "amount_sll": amount, "method": rec.get("method") or md.get("method") or "monime",
        "project": PROJECTS.get(rec.get("project") or md.get("project") or "", "General fund"),
        "order_number": session.get("orderNumber") or "", "session_id": session.get("id") or "",
    }


def verify(ref):
    """Ask Monime what really happened. → (status, session) with status in
    completed | pending | failed | unknown | error.  Only this function can
    declare a donation paid — never the browser."""
    sid, rec = find_session(ref)
    if not sid:
        return "unknown", None
    ok, code, payload = monime("GET", f"/v1/checkout-sessions/{urllib.parse.quote(sid)}")
    if not ok:
        print(f"[monime] verify {ref} failed: {monime_error(payload, code)}")
        return "error", None
    s = (payload.get("result") or {}) if isinstance(payload, dict) else {}
    status = s.get("status") or "pending"
    if status == "completed":
        if mark_completed(ref):
            info = donation_info(ref, s, rec)
            print(f"[monime] ✅ {ref} COMPLETED — {fmt_sle(sll_to_minor(info['amount_sll']) if info['amount_sll'] else 0)} from {info['email']}")
            threading.Thread(target=send_receipts, args=(info,), daemon=True).start()
        return "completed", s
    if status in ("cancelled", "expired"):
        return "failed", s
    return "pending", s


def verify_webhook_signature(raw, signature):
    if not MONIME_WEBHOOK_SECRET or not signature:
        return False
    import base64
    secret = MONIME_WEBHOOK_SECRET.encode()
    parts = dict(p.split("=", 1) for p in signature.split(",") if "=" in p) if ("=" in signature) else {}
    cands = [parts[k] for k in ("v1", "sha256", "s") if k in parts] or [signature.split("=", 1)[-1] if signature.startswith(("sha256=", "v1=")) else signature]
    payloads = [raw] + ([f"{parts['t']}.".encode() + raw] if "t" in parts else [])
    for p in payloads:
        dg = hmac.new(secret, p, hashlib.sha256)
        for c in cands:
            c = c.strip()
            if hmac.compare_digest(dg.hexdigest(), c.lower()) or hmac.compare_digest(base64.b64encode(dg.digest()).decode(), c):
                return True
    return False


# ---------------------------------------------------------------------
# Email (Gmail SMTP)
# ---------------------------------------------------------------------
def send_mail(to_addr, subject, text, html=None, to_name=""):
    msg = EmailMessage()
    msg["Subject"], msg["From"] = subject, formataddr((FROM_NAME, SMTP_USER))
    msg["To"] = formataddr((to_name, to_addr)) if to_name else to_addr
    msg["Date"], msg["Message-ID"] = formatdate(localtime=True), make_msgid(domain="gmail.com")
    msg.set_content(text)
    if html:
        msg.add_alternative(html, subtype="html")
    pw = SMTP_PASS.replace(" ", "")
    last = None
    for port, mode in ((SMTP_PORT, "starttls"), (465, "ssl")):          # try 587, fall back to 465
        for attempt in (1, 2):
            try:
                ctx = ssl_ctx()
                if mode == "ssl":
                    with smtplib.SMTP_SSL(SMTP_HOST, port, timeout=20, context=ctx) as s:
                        s.login(SMTP_USER, pw); s.send_message(msg)
                else:
                    with smtplib.SMTP(SMTP_HOST, port, timeout=20) as s:
                        s.ehlo(); s.starttls(context=ctx); s.ehlo()
                        s.login(SMTP_USER, pw); s.send_message(msg)
                print(f"[mail] ✅ sent to {to_addr} ({subject[:50]}…) via {SMTP_HOST}:{port}")
                return True
            except smtplib.SMTPAuthenticationError as e:
                print(f"[mail] ❌ Gmail rejected the App Password for {SMTP_USER}: {e}")
                return False
            except Exception as e:
                last = e
                time.sleep(1.5)
    print(f"[mail] ❌ could not send to {to_addr}: {type(last).__name__}: {last}")
    return False


def send_receipts(info):
    amt = info["amount_sll"]
    test = MONIME_MODE != "live"
    when = datetime.now().strftime("%d %B %Y at %H:%M")
    test_txt = "\nNOTE: this was a TEST transaction — no money was charged.\n" if test else ""
    test_html = ('<p style="background:#fef3c7;color:#92400e;padding:10px 14px;border-radius:6px;font-size:13px;">'
                 '<strong>Test transaction</strong> — no money was charged.</p>' if test else "")
    if valid_email(info["email"]):
        subject = f"Thank you for your donation to CBN — receipt {info['ref']}"
        text = "\n".join([
            f"Dear {info['first']},", "",
            f"Thank you! We have received your donation of {fmt_sle(sll_to_minor(amt))} (Le {amt:,}) towards {info['project']}.", "",
            f"Receipt reference : {info['ref']}", f"Amount            : {fmt_sle(sll_to_minor(amt))}",
            f"Payment method    : {info['method'].replace('_', ' ').title()}", f"Date              : {when}",
            f"Monime order      : {info['order_number'] or '—'}", test_txt,
            "100% of your gift reaches communities in Sierra Leone.", "",
            "With gratitude,", ORG_NAME, f"{OFFICE_ADDRESS} · {OFFICE_PHONE} · {OFFICE_EMAIL}",
        ])
        html = f"""<div style="font-family:Helvetica,Arial,sans-serif;max-width:600px;margin:0 auto;border:1px solid #e5e7eb;border-radius:8px;overflow:hidden;">
<div style="background:#0a2a4a;color:#fff;padding:18px 26px;font-weight:700;">Community Builders Network <span style="color:#94a3b8;font-weight:400;font-size:11px;letter-spacing:2px;">SIERRA LEONE</span></div>
<div style="height:5px;background:#16a34a;"></div>
<div style="padding:26px;color:#374151;line-height:1.65;font-size:15px;">
<h2 style="color:#0a2a4a;margin:0 0 10px;">Thank you, {_h(info['first'])}! 🎉</h2>
<p>We have received your donation of <strong>{_h(fmt_sle(sll_to_minor(amt)))}</strong> <span style="color:#6b7280;">(Le {amt:,})</span> towards <strong>{_h(info['project'])}</strong>.</p>{test_html}
<table style="width:100%;border-collapse:collapse;background:#f7f8fa;border:1px solid #e5e7eb;border-radius:6px;font-size:14px;margin:16px 0;">
<tr><td style="padding:10px 14px;color:#6b7280;width:45%;">Receipt reference</td><td style="padding:10px 14px;font-family:monospace;font-weight:700;color:#0a2a4a;">{_h(info['ref'])}</td></tr>
<tr><td style="padding:10px 14px;color:#6b7280;">Payment method</td><td style="padding:10px 14px;">{_h(info['method'].replace('_',' ').title())}</td></tr>
<tr><td style="padding:10px 14px;color:#6b7280;">Monime order</td><td style="padding:10px 14px;font-family:monospace;">{_h(info['order_number'] or '—')}</td></tr>
<tr><td style="padding:10px 14px;color:#6b7280;">Date</td><td style="padding:10px 14px;">{_h(when)}</td></tr></table>
<p>100% of your gift reaches communities in Sierra Leone.</p>
<p style="margin-top:22px;">With gratitude,<br><strong>{_h(ORG_NAME)}</strong></p></div>
<div style="padding:14px 26px;background:#f7f8fa;border-top:1px solid #e5e7eb;font-size:12px;color:#6b7280;">{_h(OFFICE_ADDRESS)} · {_h(OFFICE_PHONE)} · {_h(OFFICE_EMAIL)}</div></div>"""
        send_mail(info["email"], subject, text, html, to_name=info["name"])
    # office alert — this email IS the organisation's record of the donation
    alert = "\n".join([
        f"A donation has been confirmed by Monime ({MONIME_MODE.upper()} mode).", "",
        f"Reference : {info['ref']}", f"Amount    : {fmt_sle(sll_to_minor(amt))}  (Le {amt:,})",
        f"Donor     : {info['name']}", f"Email     : {info['email'] or '—'}",
        f"Method    : {info['method']}", f"Project   : {info['project']}",
        f"Monime    : session {info['session_id']}  order {info['order_number'] or '—'}", f"Time      : {when}",
    ])
    send_mail(OFFICE_EMAIL, f"[CBN] Donation received: {fmt_sle(sll_to_minor(amt))} from {info['name']} ({info['ref']})", alert,
              "<pre style='font-family:Helvetica,Arial,sans-serif;white-space:pre-wrap;color:#374151;line-height:1.6;'>" + _h(alert) + "</pre>",
              to_name="CBN Office")


def _h(v):
    return str(v if v is not None else "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


# ---------------------------------------------------------------------
# Shared header/footer injection (partials/header.html, partials/footer.html)
# ---------------------------------------------------------------------
def read_partial(name):
    try:
        with open(os.path.join(ROOT, "partials", f"{name}.html"), "rb") as f:
            return f.read()
    except OSError:
        return b""


def inject_partials(html, rel_path):
    header, footer = read_partial("header"), read_partial("footer")
    if not header and not footer:
        return html
    key = os.path.basename(rel_path).replace(".html", "") or "index"
    nested = "/" in rel_path.strip("/")
    if nested:                                   # /projects/x.html → make partial links root-relative
        key = rel_path.strip("/").split("/")[0]  # 'projects' / 'blog' → highlights that nav item
        if key == "blog":
            key = "news"
        fix = lambda b: re.sub(rb'(href|src)="(?!https?:|/|#|mailto:|tel:|data:)([^"]+)"', rb'\1="/\2"', b)
        header, footer = fix(header), fix(footer)
    if header:
        header = re.sub(rb'data-nav="' + key.encode() + rb'"', rb'class="active" data-nav="' + key.encode() + rb'"', header, count=1)
        header = header.replace(b'class="nav-cta" class="active"', b'class="nav-cta active"')
    html = re.sub(rb'<div data-include="header"></div>', lambda m: header, html, count=1)
    html = re.sub(rb'<div data-include="footer"></div>', lambda m: footer, html, count=1)
    return html


# ---------------------------------------------------------------------
# HTTP handler
# ---------------------------------------------------------------------
class Handler(BaseHTTPRequestHandler):
    server_version, sys_version, protocol_version = "CBN-Lite", "", "HTTP/1.1"

    def log_message(self, fmt, *args):
        print(f"[{datetime.now():%H:%M:%S}] {self.client_address[0]} {fmt % args}")

    # --- responses ---
    def _send(self, status, body=b"", ctype="text/plain; charset=utf-8", extra=()):
        if isinstance(body, str):
            body = body.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        for k, v in SECURITY_HEADERS:
            self.send_header(k, v)
        for k, v in self.cors_headers():
            self.send_header(k, v)
        for k, v in extra:
            self.send_header(k, v)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def send_json(self, data, status=200):
        self._send(status, json.dumps(data), "application/json; charset=utf-8", [("Cache-Control", "no-store")])

    def redirect(self, location):
        self._send(302, b"", extra=[("Location", location)])

    def error_page(self, status, message):
        self._send(status, f"<!DOCTYPE html><html><head><meta charset='utf-8'><title>{status}</title>"
                           f"<link rel='stylesheet' href='/styles.css'></head><body><section class='page-hero'>"
                           f"<div class='container'><h1>{status}</h1><p>{_h(message)}</p>"
                           f"<p><a href='/' class='btn btn-primary' style='color:#fff;margin-top:20px;'>← Home</a></p>"
                           f"</div></section></body></html>", "text/html; charset=utf-8")

    # --- request helpers ---
    def base_url(self):
        if PUBLIC_BASE_URL:
            return PUBLIC_BASE_URL.rstrip("/")
        scheme = "https" if self.headers.get("X-Forwarded-Proto", "").lower() == "https" else "http"
        return f"{scheme}://{self.headers.get('Host', f'{HOST}:{PORT}')}"

    def body(self, limit=65536):
        n = int(self.headers.get("Content-Length") or 0)
        if n <= 0 or n > limit:
            return b""
        return self.rfile.read(n)

    def body_data(self):
        raw = self.body()
        ct = self.headers.get("Content-Type", "")
        if "json" in ct:
            try:
                return json.loads(raw.decode("utf-8") or "{}")
            except Exception:
                return {}
        return {k: v[0] for k, v in urllib.parse.parse_qs(raw.decode("utf-8", "replace"), keep_blank_values=True).items()}

    def cors_headers(self):
        origin = self.headers.get("Origin")
        if not origin:
            return []
        if self.same_origin():
            return [("Access-Control-Allow-Origin", origin), ("Access-Control-Allow-Methods", "GET, POST, OPTIONS"), ("Access-Control-Allow-Headers", "Content-Type, Authorization, X-Requested-With"), ("Vary", "Origin")]
        return []

    def same_origin(self):
        """Accept the live frontend, Vercel previews, and the custom domain while still blocking other sites."""
        origin = self.headers.get("Origin") or self.headers.get("Referer")
        if not origin:
            return True
        origin_url = urllib.parse.urlparse(origin)
        origin_host = origin_url.netloc.lower()
        host = (self.headers.get("Host") or "").lower()
        if origin_host == host:
            return True

        origin_name = origin_url.hostname.lower() if origin_url.hostname else ""
        allowed = {urllib.parse.urlparse(o).netloc.lower() for o in ALLOWED_ORIGINS}
        if origin_host in allowed:
            return True

        if origin_name.endswith(".vercel.app"):
            return True
        if origin_name in {"cbnsl.org", "www.cbnsl.org"}:
            return True
        if origin_name.endswith(".cbnsl.org"):
            return True
        return False

    # --- routing ---
    def do_GET(self):
        path = urllib.parse.urlparse(self.path).path
        if path == "/api/donate/status":
            return self.api_status()
        if path == "/donate/return":
            return self.donate_return()
        if path == "/api/health":
            return self.send_json({"ok": True, "mode": MONIME_MODE, "space": MONIME_SPACE_ID[:12] + "…"})
        return self.serve_static(path)

    def do_HEAD(self):
        self.do_GET()

    def do_OPTIONS(self):
        self._send(204, b"", extra=[("Access-Control-Allow-Methods", "GET, POST, OPTIONS"), ("Access-Control-Allow-Headers", "Content-Type, Authorization, X-Requested-With")])

    def do_POST(self):
        path = urllib.parse.urlparse(self.path).path
        if path == "/api/donate":
            return self.api_donate()
        if path == "/api/monime/webhook":
            return self.api_webhook()
        self.error_page(404, "Not found")

    # --- static files ---
    def serve_static(self, path):
        if path in ("", "/"):
            path = "/index.html"
        safe = posixpath.normpath(urllib.parse.unquote(path)).lstrip("/")
        full = os.path.abspath(os.path.join(ROOT, safe))
        if not full.startswith(ROOT + os.sep) and full != ROOT:
            return self.error_page(403, "Forbidden")
        if not os.path.splitext(full)[1] and os.path.isfile(full + ".html"):
            full += ".html"                                         # clean URLs: /projects/<slug>
        ext = os.path.splitext(full)[1].lower()
        if ext not in ALLOWED_EXT or not os.path.isfile(full):
            return self.error_page(404, "Page not found")
        with open(full, "rb") as f:
            content = f.read()
        if ext == ".html":
            content = inject_partials(content, os.path.relpath(full, ROOT).replace(os.sep, "/"))
        mime = mimetypes.guess_type(full)[0] or "application/octet-stream"
        if ext in (".html", ".css", ".js"):
            mime += "; charset=utf-8"
        self._send(200, content, mime, [("Cache-Control", "no-cache" if ext == ".html" else "public, max-age=3600")])

    # --- donations ---
    def api_donate(self):
        ip = self.client_address[0]
        if not rate_ok("donate", ip):
            return self.send_json({"success": False, "message": "Too many attempts from your connection. Please wait a few minutes."}, 429)
        if not self.same_origin():
            return self.send_json({"success": False, "message": "Cross-site request blocked."}, 403)
        d = self.body_data()
        if clean(d.get("website")):                                   # honeypot
            return self.send_json({"success": True, "message": "Thank you!"})

        first, last = clean(d.get("first_name"), 50), clean(d.get("last_name"), 50)
        email = clean(d.get("email"), 254).lower()
        method = clean(d.get("method"), 30)
        project = clean(d.get("project"), 100)
        try:
            amount = int(str(d.get("amount", "0")).strip())
        except (TypeError, ValueError):
            amount = 0
        if method not in ("orange_money", "africell_money", "card"):
            return self.send_json({"success": False, "message": "Please choose a payment method."}, 400)
        if not first or not last:
            return self.send_json({"success": False, "message": "Please enter your first and last name."}, 400)
        if not valid_email(email):
            return self.send_json({"success": False, "message": "Please enter a valid email address for your receipt."}, 400)
        if not MIN_AMOUNT_SLL <= amount <= MAX_AMOUNT_SLL:
            return self.send_json({"success": False, "message": f"Please enter an amount between Le {MIN_AMOUNT_SLL:,} and Le {MAX_AMOUNT_SLL:,}."}, 400)
        if project and project not in PROJECTS:
            project = ""

        phone = card_holder = ""
        if method in ("orange_money", "africell_money"):
            phone, why = validate_momo(clean(d.get("phone"), 20), "orange" if method == "orange_money" else "africell")
            if not phone:
                return self.send_json({"success": False, "field": "om-phone" if method == "orange_money" else "am-phone", "message": why}, 400)
        else:
            card_holder = re.sub(r"\s+", " ", clean(d.get("card_holder"), 60)).upper()
            if len(card_holder) < 3 or " " not in card_holder or not re.match(r"^[A-Z][A-Z .'\-]{1,58}$", card_holder):
                return self.send_json({"success": False, "field": "card-holder", "message": "Please enter the full name printed on the card (letters only)."}, 400)

        with _LOCK:
            ref = "CBN-" + secrets.token_hex(3).upper()
            while ref in SESSIONS:
                ref = "CBN-" + secrets.token_hex(3).upper()
        rec = {"ref": ref, "first": first, "last": last, "email": email, "amount": amount, "method": method,
               "project": project, "phone": phone, "card_holder": card_holder, "created": datetime.now().isoformat(timespec="seconds")}
        ok, result = create_checkout(rec, self.base_url())
        if not ok:
            print(f"[monime] ❌ create checkout {ref}: {result}")
            friendly = ("The server is offline and cannot reach the payment provider. Please try again shortly."
                        if str(result).startswith("NETWORK:") else
                        "We couldn't reach the payment provider right now. Please try again in a moment.")
            return self.send_json({"success": False, "message": friendly}, 502)
        rec["session_id"] = result.get("id")
        with _LOCK:
            SESSIONS[ref] = rec
        print(f"[monime] 🧾 {MONIME_MODE.upper()} checkout {rec['session_id']} for {ref} ({fmt_sle(sll_to_minor(amount))}, {method})")
        return self.send_json({
            "success": True, "ref": ref, "mode": MONIME_MODE,
            "checkout": {"session_id": rec["session_id"], "redirect_url": result["redirectUrl"],
                         "order_number": result.get("orderNumber"), "amount_sle": fmt_sle(sll_to_minor(amount))},
            "message": "Redirecting you to the secure payment page…",
        })

    def donate_return(self):
        qs = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
        ref, outcome = clean(qs.get("ref", [""])[0], 20), clean(qs.get("outcome", [""])[0], 10)
        if not REF_RE.match(ref):
            return self.redirect("/donate.html?status=unknown")
        status, _ = verify(ref)
        if status == "completed":
            return self.redirect(f"/donate.html?status=success&ref={ref}")
        if status == "unknown":
            return self.redirect("/donate.html?status=unknown")
        if outcome == "cancel" or status == "failed":
            return self.redirect(f"/donate.html?status=cancelled&ref={ref}")
        return self.redirect(f"/donate.html?status=pending&ref={ref}")

    def api_status(self):
        if not rate_ok("status", self.client_address[0]):
            return self.send_json({"success": False, "message": "slow down"}, 429)
        qs = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
        ref = clean(qs.get("ref", [""])[0], 20)
        if not REF_RE.match(ref):
            return self.send_json({"success": False, "message": "bad reference"}, 400)
        status, s = verify(ref)
        if status == "unknown":
            return self.send_json({"success": False, "message": "unknown reference"}, 404)
        rec = SESSIONS.get(ref) or {}
        md = (s or {}).get("metadata") or {}
        try:
            amount = int(rec.get("amount") or md.get("amount_sll") or 0)
        except (TypeError, ValueError):
            amount = 0
        return self.send_json({"success": True, "ref": ref, "status": status, "mode": MONIME_MODE,
                               "amount_sll": amount, "amount_sle": fmt_sle(sll_to_minor(amount)) if amount else "",
                               "gateway_status": (s or {}).get("status"),
                               "checkout_url": (s or {}).get("redirectUrl") if status == "pending" else None})

    def api_webhook(self):
        raw = self.body(256_000)
        sig = next((self.headers.get(h) for h in ("Monime-Signature", "X-Monime-Signature", "Signature", "X-Signature") if self.headers.get(h)), "")
        verified = verify_webhook_signature(raw, sig)
        if MONIME_WEBHOOK_SECRET and not verified:
            print(f"[monime] ⛔ unsigned/invalid webhook ignored from {self.client_address[0]}")
            return self.send_json({"received": True, "verified": False}, 401)
        if not MONIME_WEBHOOK_SECRET and not rate_ok("webhook", self.client_address[0]):
            return self.send_json({"received": True, "throttled": True}, 429)
        try:
            event = json.loads(raw.decode("utf-8") or "{}")
        except Exception:
            return self.send_json({"received": False, "message": "malformed JSON"}, 400)
        obj = event.get("data") or event.get("object") or event.get("result") or event
        if isinstance(obj, dict) and isinstance(obj.get("object"), dict):
            obj = obj["object"]
        ref = (obj or {}).get("reference") or (obj or {}).get("callbackState") or ((obj or {}).get("metadata") or {}).get("donation_reference") or ""
        print(f"[monime] 🔔 webhook {event.get('event') or event.get('type') or '?'} ref={ref} signature={'OK' if verified else 'none'}")
        if REF_RE.match(str(ref)):
            threading.Thread(target=verify, args=(ref,), daemon=True).start()   # re-fetch from Monime; body itself is never trusted
        return self.send_json({"received": True, "verified": verified})


# ---------------------------------------------------------------------
# start-up
# ---------------------------------------------------------------------
def check_assets():
    """This folder is fully self-contained; warn loudly if anything is missing."""
    required = ["styles.css", "script.js", "lite.js", "article.css", "index.html", "donate.html",
                os.path.join("partials", "header.html"), os.path.join("partials", "footer.html")]
    missing = [r for r in required if not os.path.exists(os.path.join(ROOT, r))]
    if missing:
        print("  ⚠  missing files: " + ", ".join(missing))
    return not missing


def main():
    print("=" * 62)
    print("Community Builders Network - Sierra Leone  ·  LITE server")
    print("=" * 62)
    check_assets()
    load_completed()
    icon = "💳" if MONIME_MODE == "live" else "🧪"
    print(f"Site      : http://{HOST}:{PORT}/")
    print(f"Payments  : {icon} Monime {MONIME_MODE.upper()} mode · space {MONIME_SPACE_ID}")
    print(f"Receipts  : from {SMTP_USER} · alerts to {OFFICE_EMAIL}")
    print(f"Record    : {RECEIPT_LOG} ({len(COMPLETED)} completed so far)")
    print("=" * 62)

    def check():
        ok, code, payload = monime("GET", "/v1/checkout-sessions?limit=1")
        print(("✅ Monime connected" if ok else f"❌ Monime: {monime_error(payload, code)}"))
    threading.Thread(target=check, daemon=True).start()

    srv = ThreadingHTTPServer((HOST, PORT), Handler)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\nbye")
        srv.server_close()


if __name__ == "__main__":
    main()
