/**
 * Integração com o Android (Capacitor). No navegador nada disto é usado.
 *
 * O navegador interno do app não faz downloads (<a download>) nem tem o menu de
 * compartilhar da web: os PNGs vão para o cache do app e abrem o menu de
 * compartilhar do Android (Discord, Arquivos, Fotos, Drive...).
 */
import { App } from "@capacitor/app";
import { Directory, Filesystem } from "@capacitor/filesystem";
import { Share } from "@capacitor/share";

export interface PngFile {
  name: string;
  png: Blob;
}

async function toBase64(blob: Blob): Promise<string> {
  const bytes = new Uint8Array(await blob.arrayBuffer());
  let binary = "";
  const chunk = 0x8000; // String.fromCharCode com muitos argumentos estoura a pilha
  for (let i = 0; i < bytes.length; i += chunk) {
    binary += String.fromCharCode(...bytes.subarray(i, i + chunk));
  }
  return btoa(binary);
}

/** Abre o menu de compartilhar do Android com os PNGs. */
export async function shareNative(files: PngFile[]): Promise<void> {
  const uris: string[] = [];
  for (const file of files) {
    const written = await Filesystem.writeFile({
      path: `customs/${file.name}`,
      data: await toBase64(file.png),
      directory: Directory.Cache,
      recursive: true,
    });
    uris.push(written.uri);
  }
  await Share.share({ title: files.length === 1 ? files[0].name : `${files.length} customs`, files: uris });
}

/**
 * Botão "voltar" do Android: volta uma tela (o histórico do #hash); na primeira
 * tela, fecha o app (sem isto, o voltar ali não fazia nada).
 */
export function handleBackButton(): void {
  void App.addListener("backButton", ({ canGoBack }) => {
    if (canGoBack) history.back();
    else void App.exitApp();
  });
}
