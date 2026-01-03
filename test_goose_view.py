#!/usr/bin/env python3
"""
Test script to verify the goose_view function works correctly.
This tests the actual functionality without needing a full Django setup.
"""
import sys
import os

# Add the project root to Python path
sys.path.insert(0, '/Users/mz/Dropbox/_CODING/Agentic')

# Mock Django imports to test the view function
class MockRequest:
    def __init__(self):
        self.META = {}
        self.method = 'GET'

class MockDB:
    def __init__(self):
        self.closed = False
    
    def __next__(self):
        return self
    
    def close(self):
        self.closed = True

class MockDBGenerator:
    def __iter__(self):
        return self
    
    def __next__(self):
        return MockDB()

def mock_get_db():
    return MockDBGenerator()

# Mock functions that are used in the view
def _get_open_bugs_count(db):
    return 0

# Import the actual view function
try:
    from app.views.ui import goose_view
    print("✓ Successfully imported goose_view function")
    
    # Test that it can be called with a mock request
    mock_request = MockRequest()
    
    # Mock the get_db function
    import app.views.ui
    original_get_db = app.views.ui.get_db
    app.views.ui.get_db = mock_get_db
    
    # Mock _get_open_bugs_count
    original_get_open_bugs_count = app.views.ui._get_open_bugs_count
    app.views.ui._get_open_bugs_count = _get_open_bugs_count
    
    try:
        # This would normally render the template
        result = goose_view(mock_request)
        print("✓ goose_view function executes successfully")
        print(f"✓ Function returned: {type(result)}")
    except Exception as e:
        print(f"✗ goose_view function failed: {e}")
        import traceback
        traceback.print_exc()
    finally:
        # Restore original functions
        app.views.ui.get_db = original_get_db
        app.views.ui._get_open_bugs_count = original_get_open_bugs_count
        
except ImportError as e:
    print(f"✗ Failed to import goose_view: {e}")
except Exception as e:
    print(f"✗ Error during test: {e}")
    import traceback
    traceback.print_exc()
