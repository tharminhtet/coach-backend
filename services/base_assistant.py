from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional
from fastapi.responses import StreamingResponse


class BaseAssistant(ABC):

    @abstractmethod
    async def chat(
        self,
        chat_history: List[Dict[str, str]],
        user_message: str,
        purpose_data: Dict[str, Any],
        user_memories: Optional[str] = None,
    ) -> StreamingResponse:
        pass
