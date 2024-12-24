import pytest
from pathlib import Path
import os
import shutil
import time
import logging
from datetime import datetime, timedelta
from config_manager import ConfigManager

# Set up logging for tests
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

@pytest.fixture
def temp_home_dir(tmp_path):
    """Create a temporary home directory structure for testing"""
    # Create base directories
    display_dir = tmp_path / 'display_programme'
    transit_dir = tmp_path / 'brussels_transit'
    app_config_dir = transit_dir / 'app' / 'config'
    
    # Create all necessary directories
    for d in [
        display_dir,
        transit_dir,
        display_dir / 'env_backups',
        transit_dir / 'env_backups',
        app_config_dir,
        app_config_dir / 'backups'
    ]:
        d.mkdir(parents=True)
    
    # Create example files
    (display_dir / '.env.example').write_text('DISPLAY_KEY=example_value\n# Example display key')
    (transit_dir / '.env.example').write_text('TRANSIT_KEY=example_value\n# Example transit key')
    (app_config_dir / 'local.py.example').write_text('LOCAL_KEY = "example_value"\n# Example local key')
    
    return tmp_path

@pytest.fixture
def config_manager(temp_home_dir, monkeypatch):
    """Create a ConfigManager instance with mocked home directory"""
    monkeypatch.setattr(Path, 'home', lambda: temp_home_dir)
    return ConfigManager()

@pytest.fixture
def clean_backup_dir(config_manager):
    """Ensure backup directories are empty before each test"""
    # Clean up any existing backups
    for backup_dir in config_manager.backup_dirs.values():
        if backup_dir.exists():
            logger.debug(f"Cleaning backup directory: {backup_dir}")
            for backup_file in backup_dir.glob('*.backup.*'):
                try:
                    backup_file.unlink()
                    logger.debug(f"Removed existing backup: {backup_file}")
                except Exception as e:
                    logger.error(f"Failed to remove backup {backup_file}: {e}")
            backup_dir.mkdir(parents=True, exist_ok=True)
    return config_manager

def test_init_directories(config_manager, temp_home_dir):
    """Test that initialization creates all necessary directories"""
    assert (temp_home_dir / 'display_programme' / 'env_backups').exists()
    assert (temp_home_dir / 'brussels_transit' / 'env_backups').exists()
    assert (temp_home_dir / 'brussels_transit' / 'app' / 'config' / 'backups').exists()

def test_safe_path_valid(config_manager):
    """Test _safe_path with valid inputs"""
    backup_dir = config_manager.backup_dirs['display_env']
    test_file = '.env.backup.20231224160428123456'  # YYYYMMDDHHmmssxxxxxx
    path = config_manager._safe_path(backup_dir, test_file)
    assert path.parent == backup_dir
    assert path.name == test_file

def test_safe_path_traversal_attempt(config_manager):
    """Test _safe_path blocks directory traversal attempts"""
    backup_dir = config_manager.backup_dirs['display_env']
    with pytest.raises(ValueError, match="Path traversal detected in filename"):
        config_manager._safe_path(backup_dir, '../../../etc/passwd')

def test_safe_path_invalid_backup_format(config_manager):
    """Test _safe_path validates backup file format"""
    backup_dir = config_manager.backup_dirs['display_env']
    with pytest.raises(ValueError, match="Invalid backup filename format"):
        config_manager._safe_path(backup_dir, '.env.backup.invalid')

def test_read_config_nonexistent(config_manager):
    """Test reading a nonexistent config file"""
    content, variables = config_manager.read_config('display_env')
    assert content == ""
    assert variables == {}

def test_read_config_with_content(config_manager):
    """Test reading a config file with content"""
    # Create a test config file
    env_file = config_manager.config_files['display_env']
    env_file.write_text('TEST_KEY=test_value\n')
    
    content, variables = config_manager.read_config('display_env')
    assert content.strip() == 'TEST_KEY=test_value'
    assert variables == {'TEST_KEY': 'test_value'}

def test_update_config_with_backup(clean_backup_dir):
    """Test updating a config file with backup creation"""
    config_manager = clean_backup_dir
    config_type = 'display_env'
    new_content = 'NEW_KEY=new_value\n'
    
    # Force a new session by setting last_change_time to None
    config_manager.last_change_time = None
    
    # Update config and verify
    assert config_manager.update_config(config_type, new_content)
    
    # Check if backup was created
    backup_files = list(config_manager.backup_dirs[config_type].glob('*.backup.*'))
    assert len(backup_files) == 1, f"Expected 1 backup, got {len(backup_files)}"
    
    # Verify content was updated
    content, variables = config_manager.read_config(config_type)
    assert content.strip() == new_content.strip()
    assert variables == {'NEW_KEY': 'new_value'}

def test_restore_backup(config_manager):
    """Test restoring from a backup file"""
    config_type = 'display_env'
    original_content = 'ORIGINAL_KEY=original_value\n'
    new_content = 'NEW_KEY=new_value\n'
    
    # Force new session for each update
    config_manager.last_change_time = None
    config_manager.update_config(config_type, original_content)
    
    config_manager.last_change_time = None
    config_manager.update_config(config_type, new_content)
    
    # Get the backup file
    backup_files = config_manager.get_backup_files(config_type)
    assert len(backup_files) > 0
    
    # Restore from backup
    assert config_manager.restore_backup(config_type, backup_files[0].name)
    
    # Verify restoration
    content, variables = config_manager.read_config(config_type)
    assert content.strip() == original_content.strip()
    assert variables == {'ORIGINAL_KEY': 'original_value'}

def test_restore_backup_invalid_file(config_manager):
    """Test restoring from an invalid backup file"""
    with pytest.raises(ValueError, match="Invalid backup filename format"):
        config_manager.restore_backup('display_env', 'invalid.backup.file')

def test_restore_backup_nonexistent_file(config_manager):
    """Test restoring from a nonexistent backup file"""
    with pytest.raises(ValueError, match="Backup file does not exist"):
        config_manager.restore_backup('display_env', '.env.backup.20231224160428123456')

def test_get_set_value(config_manager):
    """Test getting and setting individual values"""
    config_type = 'display_env'
    
    # Set a value
    assert config_manager.set_value(config_type, 'TEST_KEY', 'test_value')
    
    # Get the value back
    value = config_manager.get_value(config_type, 'TEST_KEY')
    assert value == 'test_value'

def test_backup_rotation(clean_backup_dir):
    """Test that backup rotation works correctly"""
    config_manager = clean_backup_dir
    config_type = 'display_env'
    backup_dir = config_manager.backup_dirs[config_type]
    
    logger.debug(f"Starting backup rotation test with directory: {backup_dir}")
    
    # Create more than 5 backups with forced different timestamps
    for i in range(6, -1, -1):  # Create backups in descending order (6 to 0)
        # Force a new session for each backup
        config_manager.last_change_time = None
        content = f'TEST_KEY=value_{i}\n'
        logger.debug(f"Creating backup {i+1}/7 with content: {content.strip()}")
        config_manager.update_config(config_type, content)
        # Sleep briefly to ensure unique timestamps
        time.sleep(0.5)  # 500ms delay
    
    # List all files in backup directory
    logger.debug("Listing all files in backup directory:")
    backup_files = []
    for f in backup_dir.glob('*'):
        timestamp = f.name.split('.backup.')[1]
        content = f.read_text().strip()
        logger.debug(f"Found file: {f} (timestamp: {timestamp}, content: {content})")
        backup_files.append((f, timestamp, content))
    
    # Sort by timestamp to verify order
    backup_files.sort(key=lambda x: x[1], reverse=True)
    logger.debug("Files sorted by timestamp (newest first):")
    for f, ts, content in backup_files:
        logger.debug(f"{f.name}: {ts} -> {content}")
    
    # Check that only 5 backups are kept
    backup_files = config_manager.get_backup_files(config_type)
    assert len(backup_files) == 5, (
        f"Expected 5 backups, got {len(backup_files)}.\n"
        f"Backup files: {[str(f) for f in backup_files]}"
    )
    
    # Verify that we kept the most recent backups (last 5 values)
    backup_contents = []
    for f in backup_files:
        content = f.read_text().strip()
        mtime = datetime.fromtimestamp(f.stat().st_mtime)
        logger.debug(f"Backup {f}: content='{content}', mtime={mtime}")
        backup_contents.append(content)
    
    expected_values = [f'TEST_KEY=value_{i}' for i in range(1, 6)]  # Values 1-5
    
    # Sort both lists to compare content regardless of timestamp order
    backup_contents.sort()
    expected_values.sort()
    
    assert backup_contents == expected_values, (
        f"Backup contents don't match expected values.\n"
        f"Got: {backup_contents}\n"
        f"Expected: {expected_values}"
    )

def test_session_timeout(config_manager):
    """Test that backups are created correctly based on session timeout"""
    config_type = 'display_env'
    
    # First update should create a backup
    config_manager.update_config(config_type, 'TEST_KEY=value1\n')
    initial_backups = len(config_manager.get_backup_files(config_type))
    
    # Immediate update should not create a backup
    config_manager.update_config(config_type, 'TEST_KEY=value2\n')
    assert len(config_manager.get_backup_files(config_type)) == initial_backups 