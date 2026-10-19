# ChangeGuard: Model Switching Guide

> **Objective**: Enable any developer to replace, upgrade, or add an AI model in ChangeGuard without modifying the rest of the application.

---

## 1. Quick Switching via Configuration (No Code Changes)

If you are switching between already implemented providers (`tfidf`, `codebert`, `mock`):

### Step 1: Update `.env`
Edit your local `.env` file:
```env
# Example 1: Use TF-IDF baseline (Default, lightweight)
AI_PROVIDER=tfidf
AI_MODEL=tfidf-baseline

# Example 2: Use Pretrained CodeBERT
AI_PROVIDER=codebert
AI_MODEL=microsoft/codebert-base

# Example 3: Use Mock Provider for deterministic offline testing
AI_PROVIDER=mock
AI_MODEL=mock-jaccard
```

### Step 2: Install Any Required Libraries
- If switching to `tfidf`: `scikit-learn` and `numpy` are already in `requirements.txt`.
- If switching to `codebert`:
  ```powershell
  .\.venv\Scripts\pip install torch transformers
  ```

### Step 3: Verify the Model
Run automated tests to confirm the new model initializes properly:
```powershell
.\.venv\Scripts\pytest backend/tests/test_intent_analyzer.py -v
```

---

## 2. Adding a Completely New Model Provider

To integrate a new model (e.g. `sentence-transformers`, `UniXcoder`, or a local LLM server):

### Step 1: Implement `AIModelProvider`
Create a new file in `backend/app/intent/providers/my_new_provider.py`:

```python
from typing import Dict, Any
from backend.app.intent.provider_interface import AIModelProvider

class MyNewModelProvider(AIModelProvider):
    def __init__(self, model_name: str = "my-custom-model"):
        self._model_name = model_name

    @property
    def provider_name(self) -> str:
        return "my_provider"

    @property
    def model_name(self) -> str:
        return self._model_name

    def compute_similarity(self, text_a: str, text_b: str) -> float:
        """Calculate similarity between text_a (intent) and text_b (code hunk).

        Must return a float between 0.0 and 1.0.
        """
        # Your inference logic here
        return 0.75

    def get_model_info(self) -> Dict[str, Any]:
        return {
            "provider": self.provider_name,
            "model": self.model_name,
            "context_window": "1024 tokens",
            "hardware_requirements": "CPU / GPU",
        }
```

### Step 2: Register in `backend/app/intent/factory.py`
Open `backend/app/intent/factory.py` and register your new provider in `_instantiate_single_provider`:

```python
from backend.app.intent.providers.my_new_provider import MyNewModelProvider

def _instantiate_single_provider(provider_key: str, model_name: Optional[str]) -> AIModelProvider:
    if provider_key == "my_provider":
        return MyNewModelProvider(model_name=model_name)
    ...
```

### Step 3: Export in `backend/app/intent/providers/__init__.py`
Export your new class in `backend/app/intent/providers/__init__.py`.

---

## 3. Expected Interface Contract

Every model provider must adhere to the contract in `backend/app/intent/provider_interface.py`:

```python
class AIModelProvider(ABC):
    @property
    @abstractmethod
    def provider_name(self) -> str:
        pass

    @property
    @abstractmethod
    def model_name(self) -> str:
        pass

    @abstractmethod
    def compute_similarity(self, text_a: str, text_b: str) -> float:
        """Must return float in [0.0, 1.0]. Zero when inputs are empty."""
        pass

    @abstractmethod
    def get_model_info(self) -> Dict[str, Any]:
        pass
```

---

## 4. Verification and Testing Procedure

Whenever a model is added or changed, run the following verification checklist:

1. **Empty Input Safety**: Confirm `compute_similarity("", "") == 0.0` without throwing an unhandled exception.
2. **Boundary Checks**: Confirm return values are strictly in `[0.0, 1.0]`.
3. **Run Test Suite**:
   ```powershell
   .\.venv\Scripts\pytest backend/tests/test_intent_analyzer.py -v
   ```
4. **Update Documentation**: Log the model characteristics in `docs/AI_MODELS.md`.
