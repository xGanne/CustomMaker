package io.github.xganne.custommaker;

import android.os.Bundle;
import com.getcapacitor.BridgeActivity;

public class MainActivity extends BridgeActivity {

    @Override
    public void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        // busca e imagens do Danbooru saem do app, não do navegador interno
        // (ver DanbooruWebViewClient)
        bridge.setWebViewClient(new DanbooruWebViewClient(bridge));
    }
}
