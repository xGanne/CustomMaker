/**
 * Envio das customs ao ImgChest (igual a src/core/uploader.py): lotes de até
 * rules.imgchest.batchSize imagens por post, post oculto (só quem tem o link vê),
 * na conta do token. O ImgChest aceita o pedido direto do celular (CORS liberado).
 */
import { rules } from "./rules";

const API = "https://api.imgchest.com/v1/post";

export interface UploadFile {
  name: string;
  png: Blob;
}

export interface UploadResult {
  links: string[];
  errors: string[];
}

export class ImgChestAuthError extends Error {}

/**
 * Tempo máximo de um lote (10 imagens de ~150 KB). Numa conexão móvel que trava
 * sem dar erro, o pedido ficaria esperando para sempre; assim ele é refeito.
 */
export const BATCH_TIMEOUT_MS = 90_000;

/** `signal` do usuário + limite de tempo; `clear()` desliga o relógio. */
function attemptSignal(user: AbortSignal | undefined, timeoutMs: number): { signal: AbortSignal; clear: () => void } {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(new DOMException("tempo esgotado", "TimeoutError")), timeoutMs);
  const onAbort = () => controller.abort(user?.reason);
  if (user?.aborted) onAbort();
  else user?.addEventListener("abort", onAbort, { once: true });
  return {
    signal: controller.signal,
    clear: () => {
      clearTimeout(timer);
      user?.removeEventListener("abort", onAbort);
    },
  };
}

function isRetryable(status: number): boolean {
  return status === 429 || (status >= 500 && status <= 599);
}

async function sendBatch(files: UploadFile[], title: string, token: string, signal?: AbortSignal): Promise<Response> {
  const form = new FormData();
  form.append("title", title);
  form.append("privacy", rules.imgchest.privacy);
  form.append("nsfw", rules.imgchest.nsfw);
  // sem "anonymous": o ImgChest desativou uploads anônimos (HTTP 403)
  for (const file of files) form.append("images[]", file.png, file.name);
  return fetch(API, {
    method: "POST",
    // Accept: sem ele, um token inválido vira um redirecionamento para a página de login
    headers: { Authorization: `Bearer ${token}`, Accept: "application/json" },
    body: form,
    signal,
  });
}

/**
 * Envia em lotes; devolve os links na ordem das imagens e os erros de cada lote.
 * Cancelado (`signal`): para e devolve os links dos lotes que já subiram, como o PC.
 */
export async function uploadCustoms(
  files: UploadFile[],
  albumTitle: string,
  token: string,
  options: {
    signal?: AbortSignal;
    onProgress?: (done: number, total: number) => void;
    retries?: number;
    retryDelayMs?: number;
    timeoutMs?: number;
  } = {},
): Promise<UploadResult> {
  const cleanToken = token.trim();
  if (!cleanToken) throw new ImgChestAuthError("Configure o token do ImgChest (Configurações).");
  const batchSize = rules.imgchest.batchSize;
  const batches = Math.ceil(files.length / batchSize);
  const retries = options.retries ?? 2;
  const links: string[] = [];
  const errors: string[] = [];

  for (let start = 0; start < files.length; start += batchSize) {
    const number = start / batchSize + 1;
    if (options.signal?.aborted) {
      errors.push(`Lote ${number}: cancelado.`);
      break;
    }
    const batch = files.slice(start, start + batchSize);
    let title = batches > 1 ? `${albumTitle} (Part ${number})` : albumTitle;
    if (title.length < 3) title = `Upload_${number}`;
    let done = false;
    for (let attempt = 0; attempt <= retries && !done; attempt++) {
      if (options.signal?.aborted) break;
      const timed = attemptSignal(options.signal, options.timeoutMs ?? BATCH_TIMEOUT_MS);
      try {
        const response = await sendBatch(batch, title, cleanToken, timed.signal);
        if (response.status === 401) throw new ImgChestAuthError("Token do ImgChest inválido: confira nas Configurações.");
        if (response.ok) {
          const data = (await response.json().catch(() => null)) as { data?: { images?: { link?: string }[] } } | null;
          const found = (data?.data?.images ?? []).map((image) => image.link).filter((link): link is string => Boolean(link));
          if (found.length) links.push(...found);
          else errors.push(`Lote ${number}: enviado, mas o ImgChest não devolveu os links.`);
          done = true;
        } else if (!isRetryable(response.status) || attempt === retries) {
          const detail = (await response.text().catch(() => "")).slice(0, 200);
          errors.push(`Lote ${number}: HTTP ${response.status} ${detail}`.trim());
          done = true;
        }
      } catch (error) {
        if (error instanceof ImgChestAuthError) throw error;
        if (options.signal?.aborted) break; // cancelado: o lote não conta
        if (attempt === retries) {
          const reason = (error as Error).name === "TimeoutError" ? "demorou demais" : (error as Error).message;
          errors.push(`Lote ${number}: sem conexão com o ImgChest (${reason}).`);
          done = true;
        }
      } finally {
        timed.clear();
      }
      if (!done && !options.signal?.aborted) {
        await new Promise((resolve) => setTimeout(resolve, (options.retryDelayMs ?? 1000) * (attempt + 1)));
      }
    }
    if (!done) {
      errors.push(`Lote ${number}: cancelado.`);
      break;
    }
    options.onProgress?.(Math.min(files.length, start + batch.length), files.length);
  }
  return { links, errors };
}
