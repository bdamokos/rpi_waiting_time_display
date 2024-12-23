import pytest
from datetime import datetime, timezone
from astronomy_utils import get_moon_phase, get_daily_moon_change, get_upcoming_moon_phases
from freezegun import freeze_time

@pytest.fixture
def fixed_datetime():
    """Fixture providing a fixed datetime for consistent testing"""
    return datetime(2023, 12, 23, 12, 0, tzinfo=timezone.utc)

def test_get_moon_phase_structure():
    """Test the structure of moon phase data"""
    phase_data = get_moon_phase()
    
    assert isinstance(phase_data, dict)
    assert 'phase_angle' in phase_data
    assert 'emoji' in phase_data
    assert 'name' in phase_data
    assert 'percent_illuminated' in phase_data
    
    assert isinstance(phase_data['phase_angle'], float)
    assert isinstance(phase_data['emoji'], str)
    assert isinstance(phase_data['name'], str)
    assert isinstance(phase_data['percent_illuminated'], float)
    
    assert 0 <= phase_data['phase_angle'] <= 360
    assert 0 <= phase_data['percent_illuminated'] <= 100

@freeze_time("2023-12-23 12:00:00")
def test_get_moon_phase_specific_time(fixed_datetime):
    """Test moon phase calculation for a specific time"""
    phase_data = get_moon_phase(fixed_datetime)
    
    # The values below are specific to 2023-12-23 12:00:00 UTC
    assert isinstance(phase_data['phase_angle'], float)
    assert isinstance(phase_data['name'], str)
    assert phase_data['name'] in [
        'New Moon', 'Waxing Crescent', 'First Quarter', 
        'Waxing Gibbous', 'Full Moon', 'Waning Gibbous', 
        'Last Quarter', 'Waning Crescent'
    ]

def test_get_daily_moon_change():
    """Test daily moon change calculation"""
    change_data = get_daily_moon_change()
    
    assert isinstance(change_data, dict)
    assert 'current' in change_data
    assert 'tomorrow' in change_data
    assert 'change' in change_data
    
    assert isinstance(change_data['current'], float)
    assert isinstance(change_data['tomorrow'], float)
    assert isinstance(change_data['change'], float)
    
    # Moon moves approximately 11.6-12.7 degrees per day
    # Allow for some variation in the calculation
    assert 8 <= abs(change_data['change']) <= 15

def test_get_upcoming_moon_phases():
    """Test upcoming moon phases calculation"""
    days_ahead = 30
    phases = get_upcoming_moon_phases(days_ahead)
    
    assert isinstance(phases, list)
    assert len(phases) > 0  # Should have at least one phase in the next 30 days
    
    for phase in phases:
        assert isinstance(phase, dict)
        assert 'time' in phase
        assert 'phase_name' in phase
        assert isinstance(phase['time'], datetime)
        assert phase['phase_name'] in ['New Moon', 'First Quarter', 'Full Moon', 'Last Quarter']

def test_moon_phase_cache():
    """Test that moon phase caching works"""
    # Call twice with same timestamp
    timestamp = datetime(2023, 12, 23, 12, 0, tzinfo=timezone.utc)
    result1 = get_moon_phase(timestamp)
    result2 = get_moon_phase(timestamp)
    
    # Should return exact same object due to caching
    assert result1 is result2

def test_different_timestamps():
    """Test moon phase calculation for different timestamps"""
    timestamp1 = datetime(2023, 12, 23, 12, 0, tzinfo=timezone.utc)
    timestamp2 = datetime(2023, 12, 24, 12, 0, tzinfo=timezone.utc)
    
    phase1 = get_moon_phase(timestamp1)
    phase2 = get_moon_phase(timestamp2)
    
    # Should have different values for different days
    assert phase1['phase_angle'] != phase2['phase_angle']
    assert abs(phase1['phase_angle'] - phase2['phase_angle']) >= 10  # At least 10 degrees difference in a day