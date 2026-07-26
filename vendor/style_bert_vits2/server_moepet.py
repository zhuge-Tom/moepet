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
from io import BytesIO
from pathlib import Path
from typing import Optional

import numpy as np
import uvicorn
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from scipy.io import wavfile

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
        onnx_providers=[("CPUExecutionProvider", {"arena_extend_strategy": "kSameAsRequested"})],
    )
    model.load()  # force load now
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
        onnx_bert_models.load_model(Languages.JP)
        onnx_bert_models.load_tokenizer(Languages.JP)
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

        with BytesIO() as buf:
            wavfile.write(buf, sr, audio)
            wav_bytes = buf.getvalue()

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
