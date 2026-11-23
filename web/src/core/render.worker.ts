/// <reference lib="webworker" />
/** Faz o render da custom fora da tela (ver renderInBackground em render-client.ts). */
import { renderToBorder } from "./render";
import type { RenderRequest } from "./render-client";

self.onmessage = (event: MessageEvent<RenderRequest>) => {
  const { id, source, pos, size, bordaPos } = event.data;
  try {
    const result = renderToBorder(source, pos, size, bordaPos);
    self.postMessage({ id, result }, [result.data.buffer]);
  } catch (error) {
    self.postMessage({ id, error: String(error) });
  }
};
