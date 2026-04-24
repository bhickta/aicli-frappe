import frappe

class BaseSQLite:
    """Frappe ORM wrapper root (kept name for compatibility)."""
    def __init__(self, db_path=None):
        pass

    def close(self):
        pass
