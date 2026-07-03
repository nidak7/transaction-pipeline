from abc import ABC, abstractmethod


class LLMError(RuntimeError):
    pass


class LLMClient(ABC):
    @abstractmethod
    def generate_json(self, prompt: str) -> str:
        raise NotImplementedError
