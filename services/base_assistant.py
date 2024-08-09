from abc import ABC, abstractmethod
from typing import List, Dict, Any
from fastapi.responses import StreamingResponse


class BaseAssistant(ABC):

    @abstractmethod
    async def chat(
        self,
        chat_history: List[Dict[str, str]],
        user_message: str,
        purpose_data: Dict[str, Any],
    ) -> StreamingResponse:
        pass
