from typing import List, Dict

class ValidationError(Exception):
    """Custom exception for structured validation errors."""
    def __init__(self, errors: List[Dict]):
        self.errors = errors
        super().__init__("Validation failed")
