/**
 * Render da custom em segundo plano (Web Worker): o Lanczos de uma foto grande
 * leva centenas de ms e travaria a tela. Sem Worker (testes), roda aqui mesmo.
 */
import { renderToBorder, type Point } from "./render";
import type { Raster } from "./raster";

export interface RenderRequest {
  id: number;
  source: Raster;
  pos: Point;
  size: Point;
  bordaPos: Point;
}

type Reply = { id: number; result: Raster } | { id: number; error: string };

let worker: Worker | null | undefined;
let nextId = 0;
const pending = new Map<number, { resolve: (r: Raster) => void; reject: (e: Error) => void }>();

function getWorker(): Worker | null {
  if (worker !== undefined) return worker;
  try {
    worker = typeof Worker === "undefined"
      ? null
      : new Worker(new URL("./render.worker.ts", import.meta.url), { type: "module" });
  } catch {
    worker = null;
  }
  if (worker) {
    worker.onmessage = (event: MessageEvent<Reply>) => {
      const reply = event.data;
      const job = pending.get(reply.id);
      if (!job) return;
      pending.delete(reply.id);
      if ("error" in reply) job.reject(new Error(reply.error));
      else job.resolve(reply.result);
    };
    worker.onerror = (event) => {
      // o Worker não subiu (ou quebrou): os pedidos em aberto e os próximos rodam aqui
      event.preventDefault();
      worker?.terminate();
      worker = null;
      for (const job of pending.values()) job.reject(new Error("worker indisponível"));
      pending.clear();
    };
  }
  return worker;
}

/**
 * renderToBorder fora da tela. A imagem é copiada para o Worker (não
 * transferida): se ele falhar, o render ainda roda aqui com ela.
 */
export async function renderInBackground(source: Raster, pos: Point, size: Point, bordaPos: Point): Promise<Raster> {
  const target = getWorker();
  if (!target) return renderToBorder(source, pos, size, bordaPos);
  try {
    return await new Promise<Raster>((resolve, reject) => {
      const id = nextId++;
      pending.set(id, { resolve, reject });
      const request: RenderRequest = { id, source, pos, size, bordaPos };
      target.postMessage(request);
    });
  } catch {
    return renderToBorder(source, pos, size, bordaPos);
  }
}
