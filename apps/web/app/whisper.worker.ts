/// <reference lib="webworker" />

import {
  env,
  pipeline,
  type AutomaticSpeechRecognitionPipeline,
} from "@huggingface/transformers";

const MODEL_ID = "onnx-community/whisper-small";

env.allowRemoteModels = true;
env.allowLocalModels = false;
env.useBrowserCache = true;

let transcriber: AutomaticSpeechRecognitionPipeline | null = null;
let loading: Promise<AutomaticSpeechRecognitionPipeline> | null = null;
const createAsrPipeline = pipeline as unknown as (
  task: "automatic-speech-recognition",
  model: string,
  options: Record<string, unknown>
) => Promise<AutomaticSpeechRecognitionPipeline>;

async function createTranscriber(): Promise<AutomaticSpeechRecognitionPipeline> {
  const hasWebGpu = "gpu" in navigator;
  const common = {
    dtype: "q4" as const,
    progress_callback: (progress: Record<string, unknown>) => {
      self.postMessage({ type: "progress", progress });
    },
  };

  if (hasWebGpu) {
    try {
      return await createAsrPipeline("automatic-speech-recognition", MODEL_ID, {
        ...common,
        device: "webgpu",
      });
    } catch (error) {
      self.postMessage({
        type: "notice",
        message: "WebGPU was unavailable. Using the slower CPU fallback.",
      });
    }
  }

  return createAsrPipeline("automatic-speech-recognition", MODEL_ID, {
    ...common,
    device: "wasm",
  });
}

async function getTranscriber() {
  if (transcriber) return transcriber;
  loading ??= createTranscriber();
  transcriber = await loading;
  return transcriber;
}

self.addEventListener("message", async (event) => {
  const { type } = event.data as { type: string };

  try {
    if (type === "load") {
      await getTranscriber();
      self.postMessage({ type: "ready" });
      return;
    }

    if (type === "transcribe") {
      const { audio, language } = event.data as {
        audio: Float32Array;
        language: string;
      };
      const pipe = await getTranscriber();
      const result = await pipe(audio, {
        language,
        task: "transcribe",
        chunk_length_s: 30,
      });
      const output = Array.isArray(result) ? result[0] : result;
      self.postMessage({ type: "result", text: output?.text?.trim() || "" });
    }
  } catch (error) {
    self.postMessage({
      type: "error",
      message: error instanceof Error ? error.message : "Whisper failed",
    });
  }
});

export {};
