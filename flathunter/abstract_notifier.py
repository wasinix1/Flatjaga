"""Abstract class interface for message notifiers"""
from abc import ABC, abstractmethod

class Notifier(ABC):
    """Notifier class interface definition"""

    @abstractmethod
    def notify(self, message: str):
        """Notify users with the given message"""
