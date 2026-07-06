# Installation

SEMS is installed through **HACS** (the Home Assistant Community Store). If
you don't have HACS yet, install it first: see
[hacs.xyz/docs/use](https://hacs.xyz/docs/use/) — it's a one-time thing and
opens the door to hundreds of community integrations.

## Before you start

SEMS needs one thing to be useful: a sensor with **hourly electricity
prices**. Common sources:

- **Nord Pool** (built into Home Assistant: Settings → Devices & services →
  Add integration → Nord Pool) — provides raw market prices.
- **EnergyZero**, **Zonneplan**, **Frank Energie** or another supplier
  integration — these usually provide all-in prices (taxes included).

Optional but recommended if you have solar panels: a sensor with an **hourly
solar forecast**, e.g. **Forecast.Solar** or **Solcast**.

## Step 1 — Add SEMS as a custom repository in HACS

1. Open **HACS** in the Home Assistant sidebar.
2. Click the **three dots** in the top-right corner.
3. Choose **Custom repositories**.
4. Paste the URL of this GitHub repository (`https://github.com/NoobOnTour024/HA-SEMS`).
5. Set **Category** (or "Type") to **Integration**.
6. Click **Add** and close the dialog.

## Step 2 — Download SEMS

1. In HACS, search for **SEMS**.
2. Open it and click **Download** (bottom right).
3. **Restart Home Assistant** (Settings → System → Restart). Home Assistant
   only discovers new integrations after a restart.

## Step 3 — Add the integration

1. Go to **Settings → Devices & services**.
2. Click **+ Add integration** (bottom right).
3. Search for **SEMS** and click it.
4. The setup wizard opens:
   - **Screen 1**: pick your **electricity price entity** and (optional)
     your **PV forecast entity**.
   - **Screen 2**: prices and taxes. **The defaults work** — you can simply
     click Submit and fine-tune later. See
     [Configuration](Configuration.md) for what each field means.
5. Done! You now have a **SEMS device** with all entities under it.

## Step 4 — Check that it works

Debug mode is ON by default after installation, which gives you an extra
sensor (`sensor.sems_diagnostics`) that says in plain language what SEMS
found. Go to [Check that it works](Check-that-it-works.md) for a 5-minute
verification checklist. Once you trust the numbers, switch debug mode off
via **Settings → Devices & services → SEMS → Configure**.

## Updating

HACS notifies you when a new version is available. Click **Update** in HACS
and restart Home Assistant. Your settings are kept.
