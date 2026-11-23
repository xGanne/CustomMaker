package io.github.xganne.custommaker;

import android.net.http.HttpResponseCache;
import android.os.Bundle;
import com.getcapacitor.BridgeActivity;
import java.io.File;
import java.io.IOException;

public class MainActivity extends BridgeActivity {

    /** Cache em disco dos pedidos feitos pelo app (DanbooruWebViewClient). */
    private static final long HTTP_CACHE_BYTES = 64L * 1024 * 1024;

    @Override
    public void onCreate(Bundle savedInstanceState) {
        // As imagens do Danbooru vêm com cache de 1 ano (a busca vem com no-cache):
        // miniaturas e a imagem enquadrada não são baixadas de novo a cada uso
        if (HttpResponseCache.getInstalled() == null) {
            try {
                HttpResponseCache.install(new File(getCacheDir(), "danbooru-http"), HTTP_CACHE_BYTES);
            } catch (IOException error) {
                // sem cache: tudo continua funcionando, só baixa de novo
            }
        }
        super.onCreate(savedInstanceState);
        // busca e imagens do Danbooru saem do app, não do navegador interno
        // (ver DanbooruWebViewClient)
        bridge.setWebViewClient(new DanbooruWebViewClient(bridge));
    }
}
