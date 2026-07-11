# AGENTS.md

This file provides guidance to Codex (Codex.ai/code) when working with code in this repository.

## Project Overview

This is a Raspberry Pi project that displays bus waiting times on an e-Paper display (Waveshare 2.13" G V2). The display shows weather conditions, bus arrival times, and optionally flight tracking and ISS visibility.

## Development Environment

**Python Version**: Python 3.x
**Main Dependencies**: Flask, Pillow, requests, RPi.GPIO, waveshare-epd, pytest

For development on Mac (without hardware):
```bash
pip install -r requirements.dev.txt
```

For production on Raspberry Pi:
```bash
pip install -r requirements.txt
```

## Common Commands

### Testing
```bash
# Run all tests with coverage
pytest

# Run specific test file
pytest tests/test_weather.py

# Run with verbose output
pytest -v
```

### Code Quality
```bash
# Format code
black .

# Sort imports
isort .

# Lint code
flake8
```

### Running the Application
```bash
# Main application
python basic.py

# Debug server (for development)
python debug_server.py

# Test server
python test_server.py

# Setup/configuration web interface
python webserial_server.py
```

## Architecture

### Core Components

- **basic.py**: Main application entry point and display loop
- **display_adapter.py**: Hardware abstraction layer for e-Paper displays (includes MockDisplay for development)
- **bus_service.py**: Transit data fetching and display logic
- **weather/**: Weather service module with provider abstraction
  - **display.py**: Weather display rendering
  - **providers/**: Weather API providers (OpenWeatherMap, OpenMeteo)
- **flights.py**: Flight tracking functionality
- **webserial_server.py**: Web-based setup interface
- **token_usage.py**: Optional schedule parser and normalized token-usage client
- **token_display.py**: Compact month-to-date and rate-limit e-paper views
- **rss_service.py**, **rss_plugin.py**: RSS/Nitter polling and arbitrated notifications
- **breaking_news_service.py**, **breaking_news_plugin.py**: baseline-first breaking-news polling and arbitrated alerts
- **tools/token_usage_server.py**: Authenticated bridge for a remote usage source

### Key Design Patterns

- **Provider Pattern**: Weather services use interchangeable providers
- **Mock Objects**: MockDisplay allows development without hardware
- **Configuration**: Environment variables loaded from .env file
- **Threading**: Display operations use locks to prevent concurrent access
- **Caching**: Weather icons and data are cached for performance

### Display System

The display adapter abstracts hardware differences:
- Supports both B&W and color e-Paper displays
- Uses display_lock for thread-safe operations
- MockDisplay for development without Raspberry Pi hardware
- Dithering support for color displays

### Environment Configuration

Key environment variables:
- `weather_enabled`: Enable/disable weather display
- `transit_enabled`: Enable/disable transit times
- `screen_rotation`: Display rotation (default 90)
- `refresh_interval`: Display refresh rate (default 90s)
- `mock_display_type`: Set to 'bw', 'bwr', or 'bwry' for development
- `aeroapi_active_hours`: Time periods when AeroAPI calls are allowed (e.g., '8-18' for 8AM-6PM, '8-10,14-16,20-22' for multiple periods, '22-6' for 10PM-6AM). Use '0-24' for always active. (default: '0-24')
- `token_usage_enabled`: Opt in to token views (default: `false`)
- `display_schedule`: First-match `mode@HH:MM-HH:MM` schedule; see `docs/token-usage-display.md`
- `token_usage_source`: `http` or `file`; credentials belong only in the ignored `.env`

## Testing Strategy

- Uses pytest with fixtures for API mocking
- Tests cover weather providers, bus services, and display logic
- Coverage reports generated in htmlcov/
- Real-world data samples used in tests

## Development Notes

- Follow existing code patterns and conventions
- Don't remove comments or adjust formatting
- Test thoroughly before commits
- Use step-by-step approach for new features
- Create GitHub issues for bugs that can't be fixed quickly

## Deployment and privacy

- The public Git repository is the source of truth for application code. Keep hostnames, IP addresses, bearer tokens, account identifiers, usage snapshots, and personal `.env` values out of tracked files and commit history.
- Before deploying, confirm the target checkout is clean apart from known runtime/generated files, then use the documented update script or a fast-forward-only pull and restart `display.service`.
- Verify the deployed Git SHA, `systemctl is-active display.service`, recent service logs, and the newly rendered `debug_output.png` after restart.
- Never install Codex credentials on the display solely for token views. Prefer the read-only normalized HTTP/file interface and keep the credential-bearing collector on a better-resourced machine.
