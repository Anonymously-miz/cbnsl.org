# CBN Sierra Leone — Lite Website

A **completely separate, self-contained site**. A static site with **No database and No admin panel**

## Run it

```bash
python3 server.py          # → http://127.0.0.1:8000/
```

Python 3.8+ and nothing else — no packages to install, no other folders needed.

## What's in the folder

| File | Purpose |
|---|---|
| `server.py` | The whole backend (~400 lines): serves the pages, creates Monime checkouts, confirms payments, sends receipt emails. **Contains the Monime token and the Gmail App Password — keep this folder private.** |
| `index.html` `about.html` `projects.html` `get-involved.html` `news.html` `contact.html` | Hard-coded pages |
| `donate.html` | The donation page (amount, project, Orange / Africell / Card, Monime redirect, receipt) |
| `projects/*.html` (7) | Full project articles, hard-coded |
| `blog/*.html` (3) | Blog articles, hard-coded |
| `partials/header.html` `partials/footer.html` | Edit once — inserted into every page by the server |
| `styles.css` | The site's own stylesheet (same design as the full project, trimmed of admin-only rules) |
| `script.js` | The site's own script: mobile menu, search (Ctrl+K), EN/KR/FR switcher, counters, filter tabs — no backend calls |
| `article.css` `lite.js` | Article layout; mail-to form handling for contact / volunteer / newsletter |
| `.gitignore` | Keeps `receipts-sent.txt` and caches out of git |
| `receipts-sent.txt` | One line per paid donation (created automatically). Stops a receipt being emailed twice. Not a database — just a text file. |

## How a donation works

1. Donor fills in `donate.html` and clicks **Donate** → browser POSTs to `/api/donate`.
2. `server.py` validates the Orange/Africell number or cardholder name, creates a **Monime Checkout
   Session** (amount in SLE minor units — `Le 250,000` on the site = `SLE 250.00` = `25000`), and
   returns Monime's hosted-page URL. The donor is redirected there and pays with their PIN / card.
3. Monime sends the donor back to `/donate/return?ref=CBN-XXXXXX`. The server **asks Monime** whether
   the session is `completed` — the browser is never trusted — and only then:
   - emails a receipt to the donor,
   - emails an alert to `cbnetwork.sierraleone@gmail.com` (this is your record of the donation),
   - redirects to `donate.html?status=success`.
4. If the donor closes the browser before returning, nothing is lost: the payment is on your Monime
   dashboard, and the receipt is sent the next time that reference is verified (or instantly if you
   register a webhook — see below).

Donor details travel inside the Monime session's `metadata`, so the receipt can be rebuilt even if
the server restarted in between.

## Configuration — top of `server.py`

```python
MONIME_SPACE_ID     = "spc-k6UjAQDct7RLwT9GYqXwrpFKZ2t"
MONIME_ACCESS_TOKEN = "mon_82Oe…"
MONIME_MODE         = "test"      # change to "live" when you take real money
SMTP_USER / SMTP_PASS             # Gmail account + App Password for receipts
PUBLIC_BASE_URL     = ""          # set to "https://your-domain" when deployed
PROJECTS            = {…}         # project slugs → names shown on receipts
MIN_AMOUNT_SLL      = 5000
```

`MONIME_MODE` is a label: it puts a "test transaction" notice on receipts and in the console. Whether
money moves depends on whether the Space ID/token belong to your Monime **test** or **live** space.

## Going live

1. Put the server behind HTTPS (Caddy / nginx reverse proxy) and set `PUBLIC_BASE_URL = "https://…"`.
2. Use your **live** Space ID + token and set `MONIME_MODE = "live"`.
3. *(Optional, recommended)* In the Monime dashboard create a webhook → URL
   `https://your-domain/api/monime/webhook`, event `checkout_session.completed`, verification
   **HS256**; paste its secret into `MONIME_WEBHOOK_SECRET`. Payments are then confirmed the instant
   they happen, even if the donor never returns to the site.
4. Make a small real donation to yourself and check both emails arrive.

## Editing content

- **Text, images, projects, blog posts** → edit the HTML files directly.
- **Header / footer** → `partials/header.html` and `partials/footer.html` (changes everywhere).
- **Donation amounts / impact lines** → the `amount-grid` buttons and sidebar in `donate.html`.
- **Add a project to the donate dropdown** → add it to `PROJECTS` in `server.py` *and* to the
  `<select id="projectDesig">` in `donate.html`.
- **Contact / volunteer / newsletter forms** open the visitor's email app addressed to CBN
  (`data-mailto` on each `<form>`); there is no server processing for them by design.

## Security notes

- The Monime token never reaches the browser; all Monime calls happen in `server.py`.
- A donation is marked paid only after `server.py` re-fetches the session from `api.monime.io`.
- Per-IP rate limits on checkout creation and status polling; same-origin check on POSTs;
  honeypot field; strict security headers; only `.html/.css/.js/images` are ever served (never
  `server.py` or `receipts-sent.txt`).
- Because the secrets are hard-coded, **do not commit this folder to a public repository**.
