from abc import ABC, abstractmethod

class BaseTask(ABC):
    """Abstract Base Class for all pipeline tasks."""

    @abstractmethod
    async def run(self) -> None:
        """Executes the task asynchronously."""
        pass
