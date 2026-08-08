# Vacation privacy mode

Vacation privacy mode prevents selected display modules from appearing while
the device is visible to guests, house sitters, or other visitors. It applies
the same policy to scheduled base views, plugin claims, and private-network
display overrides.

Configure it in Advanced Settings or in `.env`:

```dotenv
vacation_mode_enabled=true
vacation_mode_sensitive_displays=calendar,token,ynab
vacation_mode_blackout_dates=2026-08-11..2026-08-14,2026-09-11..2026-09-26
vacation_mode_timezone=Europe/Brussels
vacation_mode_fallback_mode=transit
```

Date ranges are inclusive in the configured IANA timezone. A single date is
also valid. If blackout dates are blank, the enabled switch becomes a manual
always-on privacy mode.

Sensitive display names are comma-separated. A family name matches the family
and its `-`, `_`, or `:` variants, so `calendar` also suppresses
`calendar-event` and `calendar-agenda`. Shell-style patterns are supported for
broader plugin families, for example `ha:*`.

When privacy mode is active:

- sensitive scheduled views use the configured safe fallback;
- sensitive plugin claims are rejected, including claims that were already
  active when a blackout date began;
- sensitive display API overrides return a conflict instead of rendering;
- non-sensitive displays continue to rotate normally.

Invalid blackout dates or timezone names fail closed: selected sensitive
displays remain hidden until the configuration is corrected. Invalid or
sensitive fallback selections automatically move to a safe built-in display.
