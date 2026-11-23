/** Comando do Mudae que adiciona as imagens a uma custom (igual a src/core/mudae.py). */
import { rules } from "./rules";

export function mudaeCommand(title: string, links: string[]): string {
  return `$ai ${title} $\n` + links.join(" $\n");
}

/**
 * Comando dividido em mensagens que cabem no limite do Discord (2000 caracteres
 * sem Nitro). Cada parte é um $ai completo para a mesma custom.
 */
export function mudaeCommands(title: string, links: string[], limit = rules.discordMessageLimit): string[] {
  const parts: string[] = [];
  let current: string[] = [];
  for (const link of links) {
    let candidate = [...current, link];
    if (current.length && mudaeCommand(title, candidate).length > limit) {
      parts.push(mudaeCommand(title, current));
      candidate = [link];
    }
    current = candidate;
  }
  if (current.length) parts.push(mudaeCommand(title, current));
  return parts;
}

/**
 * Nome sugerido para a custom a partir das tags buscadas:
 * "hatsune_miku" -> "Hatsune Miku"; "nihilux_(honkai:_star_rail)" -> "Nihilux".
 */
export function suggestTitle(query: string): string {
  const tag = query.trim().split(/\s+/)[0] ?? "";
  const name = tag.replace(/_\(.*\)$/, "").replace(/_/g, " ").trim();
  return name.replace(/\b\p{L}/gu, (c) => c.toUpperCase());
}
