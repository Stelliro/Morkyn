# Privacy Policy — Mørkyn

**Last updated:** 2026-07-19  
**Product:** Mørkyn  
**Operator:** Stelliro  

In-app copy is also available from the app UI (Privacy) and at `/privacy`.

## 1. Our commitment

Your privacy is strictly confidential. We take security and privacy seriously.

**Mørkyn is a local-first application.** It runs on your machine. It does not require accounts, sign-ups, or personal identity. We do not collect real names, bank or card details, email for identity, or similar personal information.

**We do not track you.** There are **no analytics, no metrics pipelines, no telemetry, and no crash “phone home”** in this product. We do not build marketing profiles. We do not sell, rent, or trade player data — because we do not receive it.

## 2. What stays on your machine

Everything the app needs for play stays local unless **you** choose otherwise:

- World database and saves under your project `data/` folder  
- Campaign slots, exports you create, model traces you generate  
- Launcher preferences (`data/launcher_prefs.json`)  
- Optional API keys you enter for a **local** LLM or a **cloud model you configured** (see below)

These files are on your PC. We do not automatically upload them.

## 3. What we never collect

- Accounts, passwords, or login credentials for Mørkyn itself  
- Real names, email, phone, or postal address  
- Bank details, credit cards, or payment data  
- GPS or advertising IDs  
- Usage analytics, play metrics, or anonymous telemetry  
- Automatic crash or performance uploads  

## 4. Network activity — only when you opt in

By default, Mørkyn does **not** phone home.

### 4.1 Local play

Talking to a model on **your** computer (Ollama, llama.cpp on localhost) is local network traffic on your machine. That is not us collecting data.

### 4.2 Cloud or agent APIs you configure

If **you** set a cloud provider (for example xAI/Grok or another OpenAI-compatible API) and an API key, then **your machine** sends prompts to **that provider** under **their** privacy policy. Mørkyn is only the client you pointed at their endpoint. We do not intercept or resell that traffic.

### 4.3 Optional updates (GitHub only)

The **only** intentional “phone home” built into Mørkyn is **optional software update / rollback**, and only when **you** start it:

- Check for updates  
- Download / apply an update  
- Roll back to a previous version  

That traffic goes to **GitHub** (this project’s repository and, if used, GitHub’s release/API endpoints) so you can pull newer or older published code. There is no separate analytics server.

If you never use Update, the app does not contact GitHub for updates.

## 5. Browser extensions (uBlock Origin and similar)

Some content blockers treat local scripts (including `/static/app.js`) as trackers or block them by mistake. That can break the UI (for example missing Randomize controls) even though **this app is not tracking you**.

If the app fails to load scripts:

1. Allow `127.0.0.1` / `localhost` for this app, or  
2. Disable the blocker for this local page  

We show an in-app notice when the main script does not boot so you can fix this quickly.

## 6. Your data, your control

- Delete the `data/` folder (or individual saves) to remove local play data  
- Remove API keys from LLM Settings and your environment to stop cloud calls  
- Do not run Update if you want zero outbound GitHub contact for versioning  

## 7. Contact

- **Web:** https://stelliro.com  
- **Product:** Mørkyn  
- **Source:** https://github.com/Stelliro/Morkyn  

## 8. Short summary

**Local app. No sign-up. No personal identity collection. No tracking. No metrics. No selling data.**  
The only optional outbound product contact is **GitHub when you check for or apply updates/rollbacks**. Cloud models only talk to the provider **you** configure.
