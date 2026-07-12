# YNAB budget display

The optional YNAB integration rotates sharp 1-bit views on the 250x120 display.
It calls only YNAB's read endpoint for the current budget month. Keep the
Personal Access Token and budget ID in the ignored runtime `.env`.

```dotenv
ynab_enabled=true
ynab_access_token=replace-with-your-personal-access-token
ynab_budget_id=last-used
ynab_currency_symbol=€
ynab_views=month,daily,active,funding,exception
ynab_daily_categories=Restaurants,Groceries
ynab_funding_categories=Vacation,Drier,New laptop

ynab_glance_enabled=true
ynab_glance_poll_seconds=1
ynab_glance_interval_seconds=1800
ynab_glance_duration_seconds=60
ynab_glance_offset_seconds=900
ynab_glance_priority=20
```

The glance settings add YNAB to the normal information flow without reserving a
fixed clock-time block in `display_schedule`. With the values above, a YNAB view
appears for 60 seconds at `:15` and `:45` each hour. Successive appearances
advance through the configured `ynab_views`. The 15-minute offset avoids the
calendar agenda's default `:00` and `:30` cadence.

YNAB glances use a low-priority, non-exclusive screen claim. Upcoming calendar
events, RSS entries, flights, ISS passes, breaking news, and display overrides
can interrupt them. The normal scheduled base display is restored after the
claim ends. If YNAB has no usable snapshot, the glance is skipped; a recent
last-good snapshot may be shown with a `STALE` header.

For intentionally fixed YNAB periods, `ynab` and `ynab-always` remain supported
`display_schedule` modes. Both show the latest current-month snapshot;
`ynab-always` is provided for consistency with the token display. A recurring
glance is suppressed while either fixed YNAB mode is already scheduled. When a
fixed YNAB period is unavailable, `ynab_fallback_mode` is used.

## Calculation policy

The views follow an allocation-first model:

```text
current-month remainder = assigned this month - current-month outflows
```

The daily view divides the selected categories' current-month remainder by the
calendar days remaining, including today. The active view ranks assigned
categories by the proportion of this month's assignment already spent. The
funding view shows direct current-month contributions, not accumulated balances.
Activity in a category with no current-month assignment is flagged for review.

Category and group names are configurable.
