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
display_schedule=ynab@weekends@09:00-12:00,transit@00:00-00:00
```

`ynab` and `ynab-always` are schedule modes. Both show the latest current-month
snapshot; `ynab-always` is provided for consistency with the token display.
When YNAB is unavailable, `ynab_fallback_mode` is used. A recent last-good
snapshot may be shown with a `STALE` header.

## Calculation policy

The views follow an allocation-first model:

```text
current-month remainder = assigned this month - current-month outflows
```

Positive rollover and Ready to Assign are never included in spending guidance.
The daily view divides the selected categories' current-month remainder by the
calendar days remaining, including today. The active view ranks assigned
categories by the proportion of this month's assignment already spent. The
funding view shows direct current-month contributions, not accumulated balances.
Activity in a category with no current-month assignment is flagged for review.

Category and group names are configurable because YNAB budgets are personal and
may use localized names. The cache contains normalized category names and
amounts, so protect the display host and its filesystem accordingly.
