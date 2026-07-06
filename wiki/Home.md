# Welcome to the SEMS wiki

**SEMS (Simple Energy Management System)** is a Home Assistant integration
that tells you, for every hour of the coming day, how good that hour is for
using electricity. It combines two things you probably already have in Home
Assistant:

1. your **dynamic electricity prices** (from Nord Pool, EnergyZero,
   Zonneplan, ...), and
2. your **solar production forecast** (from Forecast.Solar, Solcast, ...).

Out of those, SEMS calculates one simple number per hour: the **score**.
A high score means using power is cheap that hour — a low price, or your
own panels covering it. A low score means using power is costly that hour.
Usually that's an expensive dark hour, but it can also be a sunny one
during an extreme price spike: exporting your solar power then earns more
than using it yourself, so consuming is better postponed.

SEMS is deliberately simple: no machine learning, no cloud, no external
connections. It reads two sensors, does honest math, and gives you numbers
you can build automations on.

## Where to go

| Page | Read it when you want to... |
|---|---|
| [Installation](Installation.md) | Install SEMS through HACS, step by step. |
| [Configuration](Configuration.md) | Understand every setting (and why the defaults are fine). |
| [How the score works](How-the-score-works.md) | Understand the calculation in plain language. |
| [Entities](Entities.md) | Know what every sensor means and which attributes exist. |
| [Example automations](Example-automations.md) | Let SEMS actually control things. |
| [Dashboard charts](Dashboard-charts.md) | Copy-paste ApexCharts cards for your dashboard. |
| [Check that it works](Check-that-it-works.md) | Verify your setup with your own eyes. |
| [FAQ](FAQ.md) | Quick answers to common questions. |

## The one-minute summary

- **You pick two sensors during setup. Everything else has working
  defaults.** SEMS works immediately.
- `sensor.sems_rank` tells you where the current hour ranks in the coming
  24 (1 = worst, 24 = best). "Rank 20 or higher" simply means "one of the 5
  best hours of the day" — perfect for automations.
- `sensor.sems_relative_score` says the same as a percentage: 0% = the
  worst hour of the coming day, 100% = the best. **Note: 100% means "best
  of the day", not "free".**
- The **balance slider** decides what "good" means: 100 = cheapest hours
  win, 0 = sunniest hours win, 50 = a fair mix (default).
- `binary_sensor.sems_free_power` switches ON when power is actually free
  (the all-in price is below zero) — useful to stop exporting solar power
  when exporting costs you money.
