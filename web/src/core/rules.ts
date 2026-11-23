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
  danbooru: {
    postFields: string;
    imageExtensions: string[];
    ratingTags: Record<string, string>;
    sortTags: Record<string, string>;
    portraitRatioTag: string;
    sampleWidth: number;
    importMinSize: [number, number];
    maxPage: number;
    autoSelectMaxPages: number;
  };
  scorer: {
    tagBoosts: Record<string, number>;
    tagPenalties: Record<string, number>;
    qualityBoosts: Record<string, number>;
    qualityPenalties: Record<string, number>;
    autoRatings: string[];
    sensitiveRatingPenalty: number;
    defaultAvoidTags: string;
    avoidTagPenalty: number;
    minAutoScore: number;
    grayscalePenalty: number;
    minColorFraction: number;
  };
}

export const rules = generated as unknown as Rules;
