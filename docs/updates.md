# Updates and Version Control

The display programme has a built-in update system that can be configured to your needs.

## Update Modes

You can control how the display programme updates itself by setting the `UPDATE_MODE` in your `.env` file:

- `none`: No automatic updates
- `releases`: Only update to new releases (recommended)
- `main`: Always update to latest main branch (may be unstable)

The default mode is `releases`, which is recommended for most users.

## Manual Updates

You can manually update your display programme in several ways:

1. Using the update script:
   ```bash
   sudo ~/display_programme/docs/service/update_display.sh
   ```
   This script will check and update all components, including system packages.

2. Using the service restart:
   ```bash
   sudo systemctl restart display.service
   ```
   This will trigger the normal update process based on your `UPDATE_MODE` setting.

3. Using git commands (for advanced users):
   ```bash
   # Stop the service
   sudo systemctl stop display.service
   
   # Update display programme
   cd ~/display_programme
   git fetch origin
   git checkout main  # or a specific release tag
   git pull
   
   # Update brussels_transit (if using local backend)
   cd ~/brussels_transit
   git fetch origin
   git checkout main  # or a specific release tag
   git pull
   
   # Restart the service
   sudo systemctl start display.service
   ```

## Checking Current Version

To check your current version:

1. Via the web interface:
   - Connect your display via USB
   - Open the [setup interface](https://bdamokos.github.io/rpi_waiting_time_display/setup/)
   - Click "Debug Server"
   - Look for the version information in the system status

2. Via command line:
   ```bash
   cd ~/display_programme
   git describe --tags
   ```

## Troubleshooting Updates

If you encounter issues during updates:

1. Check the service logs:
   ```bash
   journalctl -u display.service -f
   ```

2. Try a clean update:
   ```bash
   cd ~/display_programme
   git fetch origin
   git reset --hard origin/main  # or origin/<tag> for a specific release
   ```

3. If problems persist:
   - Make a backup of your `.env` file
   - Run the setup script again:
     ```bash
     curl -sSL https://raw.githubusercontent.com/bdamokos/rpi_waiting_time_display/main/setup_display.sh | sudo bash
     ```
   - Restore your `.env` file 