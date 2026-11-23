/** Regras geradas do código do PC (scripts/export_web_rules.py). Não duplique valores aqui. */
import generated from "../generated/rules.json";

export type BorderStyle = "simples" | "dupla" | "brilho" | "degrade" | "sombra";

export interface Rules {
  border: { width: number; height: number; thickness: number };
  colors: Record<string, string>;
  styles: Record<BorderStyle, string>;
  defaultStyle: BorderStyle;
  masks: { file: string; order: string[] };
  discordMessageLimit: number;
}

export const rules = generated as unknown as Rules;
