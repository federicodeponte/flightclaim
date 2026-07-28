# Running this as an agent

The Python package is deliberately offline: it decides, calculates and drafts, but it does
not touch your accounts. Everything in this file is about the layer *around* it — what you
have to connect if you want an agent to actually run a claim for months without you.

Nothing here is required to use the library. Connect only what you need.

## What the library does and does not do

| | Library (`flightclaim/`) | Needs a connection |
|---|---|---|
| Decide entitlement, compute amounts | yes | no |
| Draft claim / rejection-reply / regulator letters | yes | no |
| Send an email to the airline | no | mailbox |
| Watch for replies over months | no | mailbox |
| Submit a regulator web form | no | browser |
| Post a certified physical letter | no | postal provider (manual) |

## 1. Mailbox connection (the one that actually matters)

A claim is won or lost on correspondence. You need read access to see replies and, if you
choose, send access to file and follow up.

`watcher/watch_claim.py` uses plain IMAP. Copy `watcher/config.example.json` to
`watcher/config.json` (gitignored) and fill in host, user and an **app password** — not your
account password. Then schedule it:

```
23 8 * * *  /usr/bin/python3 /path/to/watcher/watch_claim.py >> /path/to/cron.log 2>&1
```

If you drive it from an agent framework instead of cron, use whatever mail integration that
framework already has (Gmail API, Microsoft Graph, an MCP mail server). The rules below matter
more than the transport.

### Two failure modes that will silently cost you the case

1. **Reading the wrong mailbox.** If your integration authenticates to a different account
   than the one receiving the correspondence, every poll returns "nothing new" and looks
   healthy. The watcher checks the connected mailbox identity against `expected_mailbox`
   and refuses to report silence when they disagree.
2. **Treating a broken poll as good news.** Auth expiry, a revoked app password, a changed
   default connection — all of these produce zero results, which is indistinguishable from
   "no reply yet". The watcher tracks a baseline: if it previously saw case mail and now sees
   none, it alerts instead of reassuring you.

Both are implemented, and both exist because they happened. An agent that says "no news"
when it is blind is worse than no agent.

## 2. Browser automation (for regulator portals)

Several national enforcement bodies only accept complaints and status enquiries through a web
form. Those forms are ordinary public pages, so any browser-automation tool works —
Playwright, browser-use, an MCP browser server, or a human with a mouse.

Practical notes from real filings:

- Forms often reveal **conditional required fields** after you pick a category. Snapshot the
  page again after every selection instead of filling blind.
- Date pickers commonly reject typed input and only accept a click on the day cell.
- Consent banners and privacy checkboxes are frequently hidden behind styled labels; click
  the `<label>`, not the invisible `<input>`.
- Some portals require a national eID or a foreigner e-signature account. Registration can
  take days. Check this *before* you plan around online filing.
- Datacentre IPs get bot-walled by some airline and travel-agency sites. Regulator sites are
  usually fine; airline self-service portals often are not.

## 3. The approval boundary (do not automate this away)

Read and draft automatically. Do **not** let an agent send on your behalf to an airline, a
regulator or a consumer body without you seeing the exact text first.

- A filing to a regulator can be **binding**, and in several jurisdictions choosing one forum
  forecloses the others. That is not a decision to delegate to a retry loop.
- Duplicate or out-of-context sends damage credibility with the case handler.
- Before any send, read the existing thread. Airline ticketing systems silently drop new
  emails on a rejected case, so replies must stay in-thread.

The watcher enforces the read-only half of this: it never replies to anyone. It notifies you
and stops.

## 4. Keep a ledger

Whatever you automate, keep one file per case recording: date filed, channel, reference
number, expected response window, next action date. Claims run for months across three or
four channels at once. The ledger, not your memory, is what survives.

## 5. Secrets

Credentials live in `watcher/config.json`, which is gitignored, or in your framework's secret
store. Never commit them, never paste them into an issue, and prefer app passwords or scoped
tokens over account passwords so you can revoke access without changing your login.
