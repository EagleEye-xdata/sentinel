from pathlib import Path
from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parents[2]

class Settings(BaseSettings):
    database_url: str = f"sqlite:///{ROOT / 'promptguard.db'}"
    redis_url: str = "redis://localhost:6379/0"
    judge_provider: str = "none"
    judge_model: str = "gpt-4o-mini"
    openai_judge_model: str = "gpt-4o-mini"
    anthropic_judge_model: str = "claude-3-5-haiku-latest"
    google_judge_model: str = "gemini-2.0-flash"
    openai_api_key: str | None = None
    anthropic_api_key: str | None = None
    google_api_key: str | None = None
    encryption_key: str = Field(default="",validation_alias=AliasChoices("SENTINEL_ENCRYPTION_KEY","EAGLEI_ENCRYPTION_KEY","ENCRYPTION_KEY"))
    cors_origins: str = Field(default="http://localhost:5173",validation_alias=AliasChoices("SENTINEL_CORS_ORIGINS","EAGLEI_CORS_ORIGINS","CORS_ORIGINS"))
    proxy_api_key: str = Field(default="",validation_alias=AliasChoices("SENTINEL_PROXY_API_KEY","EAGLEI_PROXY_API_KEY","PROXY_API_KEY"))
    demo_target_url: str = "http://localhost:8001/v1/chat/completions"

    # Hugging Face credentials. These are read from .env via pydantic-settings,
    # which does NOT export them to os.environ -- adapters must read them from here.
    hf_token: str = Field(default="",validation_alias=AliasChoices("HF_TOKEN","HUGGINGFACE_TOKEN"))
    hf_model_id: str = "mistralai/Mistral-7B-Instruct-v0.3"
    hf_router_url: str = "https://router.huggingface.co/hf-inference/v1/chat/completions"
    canary_secret: str = "GENESIS-7731-INTERNAL"
    mock_llm: bool = False

    # --- Plane 4: cryptographic audit -------------------------------------
    # Sealed segment keys are published here (atomically) so the chain can be
    # verified offline by anyone holding the published key file.
    audit_key_dir: str = str(ROOT / "data" / "audit_keys")

    # --- Air-gapped micro-model sandbox -----------------------------------
    # Point MICRO_MODEL_PATH at a local quantized GGUF (e.g. TinyLlama-1.1B-Chat
    # Q4_K_M) to run internal:// targets on a real local model. Left blank, the
    # sandbox falls back to its deterministic offline oracle.
    micro_model_path: str = Field(default="", validation_alias=AliasChoices("MICRO_MODEL_PATH", "SENTINEL_MICRO_MODEL_PATH", "EAGLEI_MICRO_MODEL_PATH"))
    micro_model_ctx: int = 2048
    micro_model_threads: int = 0
    micro_model_gpu_layers: int = 0
    micro_model_max_tokens: int = 320

    # --- Response DLP ------------------------------------------------------
    dlp_redact_threshold: float = 30.0
    dlp_block_threshold: float = 70.0
    entropy_threshold: float = 4.0
    entropy_min_len: int = 20

    # env_file is resolved against ROOT so the app picks up .env regardless of cwd.
    model_config = SettingsConfigDict(env_file=ROOT / ".env", extra="ignore")

settings = Settings()
