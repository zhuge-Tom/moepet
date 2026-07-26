"""
Moepet Style-Bert-VITS2 ONNX inference server.
Minimal FastAPI server optimized for CPU ONNX inference with clause streaming.

Usage:
    python server_moepet.py --port 5001
"""
from __future__ import annotations

import argparse
import os
import sys
import time
import wave
from collections import OrderedDict
from io import BytesIO
from pathlib import Path
from typing import Optional

import numpy as np
import uvicorn
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response

# ── Add parent to path so style_bert_vits2 imports work ──
HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

from style_bert_vits2.constants import (
    DEFAULT_LENGTH,
    DEFAULT_SDP_RATIO,
    DEFAULT_NOISE,
    DEFAULT_NOISEW,
    DEFAULT_STYLE,
    DEFAULT_STYLE_WEIGHT,
    Languages,
)
from style_bert_vits2.logging import logger
from style_bert_vits2.nlp import onnx_bert_models
from style_bert_vits2.nlp.japanese import pyopenjtalk_worker as pyopenjtalk
from style_bert_vits2.nlp.japanese.user_dict import update_dict
from style_bert_vits2.tts_model import TTSModel


# ── Globals ──
MODEL: Optional[TTSModel] = None
MODEL_LOADED = False

# Short interjections ("うん。", "そうだね。"…) repeat constantly in chat and
# still pay ~1s of fixed model cost each. Cache finished WAVs for short texts;
# longer sentences rarely repeat and keep their natural per-render variation.
WAV_CACHE: "OrderedDict[tuple, bytes]" = OrderedDict()
WAV_CACHE_LIMIT = 96
WAV_CACHE_MAX_CHARS = 24

ONNX_PROVIDERS = [("CPUExecutionProvider", {"arena_extend_strategy": "kSameAsRequested"})]


def load_japanese_bert() -> None:
    """Load the JP BERT session tuned for per-request latency.

    The upstream loader targets low-memory machines: it disables the CPU
    memory arena and all graph optimization, which costs roughly 150 ms per
    request on this dedicated inference server. Build the session with both
    enabled and register it in the upstream cache; fall back to the stock
    loader if the private cache layout ever changes.
    """
    import onnxruntime

    bert_dir = HERE / "bert" / "deberta-v2-large-japanese-char-wwm-onnx"
    try:
        registry = onnx_bert_models.__dict__["__loaded_models"]
        sess_options = onnxruntime.SessionOptions()
        sess_options.graph_optimization_level = (
            onnxruntime.GraphOptimizationLevel.ORT_ENABLE_ALL)
        sess_options.log_severity_level = 3
        sess_options.enable_cpu_mem_arena = True
        t0 = time.time()
        registry[Languages.JP] = onnxruntime.InferenceSession(
            str(bert_dir / "model_fp16.onnx"),
            sess_options=sess_options,
            providers=ONNX_PROVIDERS,
        )
        logger.info(f"JP BERT loaded (optimized) in {time.time() - t0:.1f}s")
    except (KeyError, TypeError):
        onnx_bert_models.load_model(Languages.JP, enable_cpu_mem_arena=True)
    onnx_bert_models.load_tokenizer(Languages.JP)


def load_noir_model(model_dir: Path, device: str = "cpu") -> TTSModel:
    """Load the Noir ONNX model."""
    global MODEL, MODEL_LOADED

    onnx_path = model_dir / "noir" / "noir.onnx"
    config_path = model_dir / "noir" / "config.json"
    style_path = model_dir / "noir" / "style_vectors.npy"

    if not onnx_path.exists():
        raise FileNotFoundError(f"ONNX model not found: {onnx_path}")
    if not config_path.exists():
        raise FileNotFoundError(f"Config not found: {config_path}")
    if not style_path.exists():
        raise FileNotFoundError(f"Style vectors not found: {style_path}")

    logger.info(f"Loading ONNX model from {onnx_path}...")
    t0 = time.time()

    model = TTSModel(
        model_path=onnx_path,
        config_path=config_path,
        style_vec_path=style_path,
        device=device,
        onnx_providers=ONNX_PROVIDERS,
    )
    if device == "cpu":
        # TTSModel.load() would disable graph optimization for CPU sessions.
        # Build the acoustic session directly so short clauses shave off the
        # optimization the stock loader skips.
        import onnxruntime

        sess_options = onnxruntime.SessionOptions()
        sess_options.graph_optimization_level = (
            onnxruntime.GraphOptimizationLevel.ORT_ENABLE_ALL)
        sess_options.log_severity_level = 3
        onnxruntime.set_default_logger_severity(3)
        model.onnx_session = onnxruntime.InferenceSession(
            str(onnx_path),
            sess_options=sess_options,
            providers=ONNX_PROVIDERS,
        )
    else:
        model.load()
    logger.info(f"Model loaded in {time.time() - t0:.1f}s")

    MODEL = model
    MODEL_LOADED = True
    return model


def ensure_model() -> TTSModel:
    """Lazy-load the model if not already loaded."""
    global MODEL
    if MODEL is None:
        raise RuntimeError("Model not loaded. Server must be initialized first.")
    return MODEL


# ── App factory ──
def create_app(model_dir: Path, port: int, device: str = "cpu") -> FastAPI:
    app = FastAPI(title="Moepet SBV2 TTS", version="1.0.0")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Pre-load model on startup
    @app.on_event("startup")
    async def startup():
        # Init pyopenjtalk worker
        pyopenjtalk.initialize_worker()
        update_dict()
        # ONNX acoustic inference also needs an ONNX Japanese BERT model.
        # Load both pieces before reporting healthy so the first speech request
        # is fast and a corrupt/missing BERT asset fails during startup.
        load_japanese_bert()
        # Load TTS model
        model = load_noir_model(model_dir, device)
        # ONNX Runtime performs additional graph and memory setup on the first
        # inference. Pay that cost during Moepet's background prewarm instead
        # of after the first visible chat reply.
        warmup_started = time.time()
        model.infer(
            text="あ。",
            language=Languages.JP,
            speaker_id=0,
            line_split=False,
            style=DEFAULT_STYLE,
            style_weight=DEFAULT_STYLE_WEIGHT,
        )
        logger.info(f"First-inference warmup completed in {time.time() - warmup_started:.1f}s")
        logger.info(f"Server ready on port {port}")

    @app.post("/tts")
    async def tts(request: Request):
        """
        Synthesize speech from text.

        JSON body:
            text: str          - Japanese text to synthesize
            speed: float = 1.0 - Speed factor (0.5-2.0, lower=faster)
            style: str = "Neutral" - Voice style
            style_weight: float = 1.0

        Returns: audio/wav
        """
        try:
            body = await request.json()
        except Exception:
            raise HTTPException(400, "Invalid JSON body")

        text = body.get("text", "").strip()
        if not text:
            raise HTTPException(400, "text is required")

        speed = float(body.get("speed", 1.0))
        speed = max(0.5, min(speed, 2.0))
        # Speed -> length (inverse relationship): faster = lower length
        length = 1.0 / speed

        style = body.get("style", "Neutral")
        style_weight = float(body.get("style_weight", 1.0))

        cache_key = None
        if len(text) <= WAV_CACHE_MAX_CHARS:
            cache_key = (text, round(speed, 3), style, round(style_weight, 2))
            cached = WAV_CACHE.get(cache_key)
            if cached is not None:
                WAV_CACHE.move_to_end(cache_key)
                logger.info(f"TTS cache hit: {len(text)} chars")
                return Response(content=cached, media_type="audio/wav")

        model = ensure_model()

        t0 = time.time()
        sr, audio = model.infer(
            text=text,
            language=Languages.JP,
            speaker_id=0,
            sdp_ratio=DEFAULT_SDP_RATIO,
            noise=DEFAULT_NOISE,
            noise_w=DEFAULT_NOISEW,
            length=length,
            line_split=False,
            style=style,
            style_weight=style_weight,
        )
        elapsed = time.time() - t0
        audio_duration = len(audio) / sr
        logger.info(f"TTS: {len(text)} chars -> {audio_duration:.1f}s audio in {elapsed:.1f}s (RTF={elapsed/audio_duration:.2f})")

        # TTSModel.infer already converts to int16; the stdlib writer keeps
        # scipy out of the minimal inference environment.
        pcm = np.asarray(audio, dtype=np.int16)
        with BytesIO() as buf:
            with wave.open(buf, "wb") as wav:
                wav.setnchannels(1)
                wav.setsampwidth(2)
                wav.setframerate(int(sr))
                wav.writeframes(pcm.tobytes())
            wav_bytes = buf.getvalue()

        if cache_key is not None:
            WAV_CACHE[cache_key] = wav_bytes
            while len(WAV_CACHE) > WAV_CACHE_LIMIT:
                WAV_CACHE.popitem(last=False)

        return Response(content=wav_bytes, media_type="audio/wav")

    @app.get("/health")
    async def health():
        return {"status": "ok", "model_loaded": MODEL_LOADED}

    return app


# ── Main ──
if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", "-p", type=int, default=5001)
    parser.add_argument("--model-dir", "-d", type=str, default=None)
    parser.add_argument("--device", type=str, default="cpu")
    args = parser.parse_args()

    model_dir = Path(args.model_dir) if args.model_dir else HERE / "model_assets"

    app = create_app(model_dir=model_dir, port=args.port, device=args.device)

    logger.info(f"Starting Moepet SBV2 server on http://127.0.0.1:{args.port}")
    logger.info(f"API docs: http://127.0.0.1:{args.port}/docs")
    uvicorn.run(app, port=args.port, host="127.0.0.1", log_level="warning")
