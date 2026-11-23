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

/** Envia em lotes; devolve os links na ordem das imagens e os erros de cada lote. */
export async function uploadCustoms(
  files: UploadFile[],
  albumTitle: string,
  token: string,
  options: { signal?: AbortSignal; onProgress?: (done: number, total: number) => void; retries?: number; retryDelayMs?: number } = {},
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
    const batch = files.slice(start, start + batchSize);
    let title = batches > 1 ? `${albumTitle} (Part ${number})` : albumTitle;
    if (title.length < 3) title = `Upload_${number}`;
    let done = false;
    for (let attempt = 0; attempt <= retries && !done; attempt++) {
      if (options.signal?.aborted) throw new DOMException("cancelado", "AbortError");
      try {
        const response = await sendBatch(batch, title, cleanToken, options.signal);
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
        if (error instanceof ImgChestAuthError || (error as Error).name === "AbortError") throw error;
        if (attempt === retries) {
          errors.push(`Lote ${number}: sem conexão com o ImgChest (${(error as Error).message}).`);
          done = true;
        }
      }
      if (!done) await new Promise((resolve) => setTimeout(resolve, (options.retryDelayMs ?? 1000) * (attempt + 1)));
    }
    options.onProgress?.(Math.min(files.length, start + batch.length), files.length);
  }
  return { links, errors };
}
